import json
import re
from typing import Any, TypedDict

from langchain_core.messages import HumanMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI
from langgraph.graph import END, StateGraph

from backend.config import get_settings


class AnalysisState(TypedDict, total=False):
    transcript: str
    participants: list[str]
    cleaned_transcript: str
    intent_notes: str
    candidate_tasks: list[dict[str, str]]
    action_items: list[dict[str, str]]
    summary: str


def _clean_transcript(state: AnalysisState) -> AnalysisState:
    raw = state.get("transcript", "")
    cleaned = re.sub(r"\s+", " ", raw).strip()
    cleaned = re.sub(r"\b(uh|um|like|you know)\b", "", cleaned, flags=re.IGNORECASE)
    return {**state, "cleaned_transcript": cleaned.strip()}


def _fallback_analysis(text: str, participants: list[str]) -> tuple[str, list[dict[str, str]], str]:
    sentences = re.split(r"(?<=[.!?])\s+", text)
    tasks: list[dict[str, str]] = []
    intent = "Action-oriented discussion"

    for sentence in sentences:
        lowered = sentence.lower()
        if any(
            token in lowered
            for token in [
                "will",
                "should",
                "action",
                "todo",
                "follow up",
                "deadline",
                "assign",
                "need to",
                "please",
            ]
        ):
            assignee = ""
            
            # Try to extract name patterns like "Alice should..." or "Bob will..." FIRST (more reliable)
            name_patterns = [
                r"^([A-Z][a-z]+)\s+(should|will|needs to|must|has to)\b",
                r"\b([A-Z][a-z]+)\s+(should|will|needs to|must|has to)\b"
            ]
            for pattern in name_patterns:
                name_match = re.search(pattern, sentence)
                if name_match:
                    assignee = name_match.group(1)
                    break
            
            # Fallback: check if any participant appears in the sentence
            if not assignee and participants:
                for p in participants:
                    if p.lower() in lowered:
                        assignee = p
                        break
            
            deadline_match = re.search(
                r"\b(by\s+[A-Za-z0-9\-\s,]+|tomorrow|next\s+week|friday|monday|tuesday|wednesday|thursday|saturday|sunday|eod|end of day|\d{4}-\d{2}-\d{2})\b",
                sentence,
                flags=re.IGNORECASE,
            )
            tasks.append(
                {
                    "task": sentence.strip()[:180],
                    "assignee": assignee,
                    "deadline": deadline_match.group(0) if deadline_match else "",
                }
            )

    if not tasks and sentences:
        tasks.append({"task": sentences[0][:160], "assignee": "", "deadline": ""})

    summary = " ".join(sentences[:4]).strip()[:650]
    return intent, tasks[:10], summary


def _extract_task_metadata(task_text: str, participants: list[str]) -> dict[str, str]:
    text = (task_text or "").strip()
    lowered = text.lower()

    assignee = ""
    for participant in participants or []:
        participant_name = str(participant or "").strip()
        if participant_name and participant_name.lower() in lowered:
            assignee = participant_name
            break

    if not assignee:
        name_patterns = [
            r"^([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\s+(should|will|needs to|must|has to|to)\b",
            r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\s+(should|will|needs to|must|has to|to)\b",
            r"assign(?:ed|ing)?\s+to\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)",
        ]
        for pattern in name_patterns:
            match = re.search(pattern, text)
            if match:
                assignee = match.group(1).strip()
                break

    deadline_match = re.search(
        r"\b(by\s+[A-Za-z0-9\-\s,]+|tomorrow|next\s+week|this\s+week|friday|monday|tuesday|wednesday|thursday|saturday|sunday|eod|end of day|\d{4}-\d{2}-\d{2})\b",
        text,
        flags=re.IGNORECASE,
    )

    return {
        "task": text[:180],
        "assignee": assignee,
        "deadline": deadline_match.group(0) if deadline_match else "",
    }


def _chat_model() -> ChatOpenAI | None:
    settings = get_settings()
    google_key = (settings.gemini_api_key or settings.google_api_key or "").strip()
    if google_key:
        return ChatGoogleGenerativeAI(model="gemini-1.5-pro", temperature=0, google_api_key=google_key)

    openai_key = (settings.openai_api_key or "").strip()
    if openai_key and openai_key.startswith("sk-"):
        return ChatOpenAI(model="gpt-4o", temperature=0, api_key=openai_key)

    return None


def _extract_intent(state: AnalysisState) -> AnalysisState:
    cleaned = state.get("cleaned_transcript", "")
    participants = state.get("participants", [])
    model = _chat_model()

    if not model:
        intent, _, _ = _fallback_analysis(cleaned, participants)
        return {**state, "intent_notes": intent}

    prompt = (
        "You are an assistant that identifies meeting intent. "
        "Return one concise sentence explaining the meeting's core intent.\n\n"
        f"Participants: {participants}\n"
        f"Transcript:\n{cleaned}"
    )
    response = model.invoke([HumanMessage(content=prompt)])
    return {**state, "intent_notes": response.content.strip()}


def _identify_tasks(state: AnalysisState) -> AnalysisState:
    cleaned = state.get("cleaned_transcript", "")
    participants = state.get("participants", [])
    model = _chat_model()

    if not model:
        _, tasks, _ = _fallback_analysis(cleaned, participants)
        return {**state, "candidate_tasks": tasks}

    prompt = (
        "Extract concrete tasks from this meeting transcript. "
        "Return STRICT JSON only with key tasks, where tasks is an array of strings. "
        "Each task string must contain action + owner + due date when available.\n\n"
        f"Transcript:\n{cleaned}"
    )

    response = model.invoke([HumanMessage(content=prompt)])
    text = str(response.content).strip()

    tasks: list[dict[str, str]] = []
    try:
        parsed = json.loads(text)
        for task_text in parsed.get("tasks", [])[:20]:
            tasks.append(_extract_task_metadata(str(task_text), participants))
    except json.JSONDecodeError:
        _, fallback_tasks, _ = _fallback_analysis(cleaned, participants)
        tasks = fallback_tasks

    return {**state, "candidate_tasks": tasks}


def _assign_tasks(state: AnalysisState) -> AnalysisState:
    tasks = state.get("candidate_tasks", [])
    participants = state.get("participants", [])
    cleaned = state.get("cleaned_transcript", "")

    if not tasks:
        return {**state, "action_items": []}

    model = _chat_model()
    if not model:
        assigned = []
        for task in tasks:
            assignee = ""
            for p in participants:
                if p.lower() in cleaned.lower() and p.lower() in task["task"].lower():
                    assignee = p
                    break
            assigned.append(
                {
                    "task": task["task"],
                    "assignee": assignee,
                    "deadline": task.get("deadline", ""),
                }
            )
        return {**state, "action_items": assigned[:15]}

    prompt = (
        "Assign the most likely owner and deadline for each task from the transcript context. "
        "Return STRICT JSON with key action_items as array of objects {task, assignee, deadline}.\n\n"
        f"Participants: {participants}\n"
        f"Tasks: {json.dumps(tasks)}\n"
        f"Transcript:\n{cleaned}"
    )
    response = model.invoke([HumanMessage(content=prompt)])
    text = str(response.content).strip()

    action_items: list[dict[str, str]] = []
    try:
        parsed = json.loads(text)
        for item in parsed.get("action_items", [])[:20]:
            task_text = str(item.get("task", "")).strip()
            normalized = _extract_task_metadata(task_text, participants)
            assignee = str(item.get("assignee", "")).strip() or normalized["assignee"]
            deadline = str(item.get("deadline", "")).strip() or normalized["deadline"]
            action_items.append(
                {
                    "task": task_text,
                    "assignee": assignee,
                    "deadline": deadline,
                }
            )
    except json.JSONDecodeError:
        action_items = tasks

    enriched_items: list[dict[str, str]] = []
    for item in action_items:
        enriched = _extract_task_metadata(item.get("task", ""), participants)
        enriched_items.append(
            {
                "task": enriched["task"],
                "assignee": item.get("assignee", "").strip() or enriched["assignee"],
                "deadline": item.get("deadline", "").strip() or enriched["deadline"],
            }
        )

    return {**state, "action_items": [i for i in enriched_items if i.get("task")]}


def _generate_summary(state: AnalysisState) -> AnalysisState:
    cleaned = state.get("cleaned_transcript", "")
    participants = state.get("participants", [])
    action_items = state.get("action_items", [])
    intent = state.get("intent_notes", "")

    model = _chat_model()
    if not model:
        _, _, fallback_summary = _fallback_analysis(cleaned, participants)
        summary = f"Intent: {intent}. Summary: {fallback_summary}".strip()
        return {**state, "summary": summary}

    prompt = (
        "Generate a concise meeting summary in 4-6 bullet-style sentences as plain text. "
        "Include key decisions, blockers, and next steps.\n\n"
        f"Intent: {intent}\n"
        f"Participants: {participants}\n"
        f"Action items: {json.dumps(action_items)}\n"
        f"Transcript:\n{cleaned}"
    )
    response = model.invoke([HumanMessage(content=prompt)])
    return {**state, "summary": str(response.content).strip()}


def _build_graph():
    graph = StateGraph(AnalysisState)
    graph.add_node("clean_transcript", _clean_transcript)
    graph.add_node("extract_intent", _extract_intent)
    graph.add_node("identify_tasks", _identify_tasks)
    graph.add_node("assign_tasks", _assign_tasks)
    graph.add_node("generate_summary", _generate_summary)

    graph.set_entry_point("clean_transcript")
    graph.add_edge("clean_transcript", "extract_intent")
    graph.add_edge("extract_intent", "identify_tasks")
    graph.add_edge("identify_tasks", "assign_tasks")
    graph.add_edge("assign_tasks", "generate_summary")
    graph.add_edge("generate_summary", END)

    return graph.compile()


_ANALYSIS_GRAPH = _build_graph()


def run_analysis(transcript: str, participants: list[str]) -> dict[str, Any]:
    try:
        result = _ANALYSIS_GRAPH.invoke({"transcript": transcript, "participants": participants})
        return {
            "summary": result.get("summary", ""),
            "action_items": result.get("action_items", []),
        }
    except Exception:
        _, action_items, summary = _fallback_analysis(transcript, participants)
        return {
            "summary": summary,
            "action_items": action_items,
        }
