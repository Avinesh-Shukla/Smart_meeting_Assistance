import React from "react";

export default function TaskPanel({ items, onChange, onSave }) {
  function updateItem(index, field, value) {
    const next = items.map((item, i) => (i === index ? { ...item, [field]: value } : item));
    onChange(next);
  }

  function addItem() {
    onChange([...items, { task: "", assignee: "", deadline: "" }]);
  }

  return (
    <section className="sma-card">
      <div className="sma-title-row">
        <h3>Action Items</h3>
        <button type="button" className="sma-btn-small" onClick={addItem}>
          Add
        </button>
      </div>
      <div className="sma-scroll-area">
        {items.length === 0 && <p className="sma-empty">No tasks yet.</p>}
        {items.map((item, index) => (
          <div className="sma-task" key={`${index}-${item.task}`}>
            <input
              value={item.task || ""}
              onChange={(e) => updateItem(index, "task", e.target.value)}
              placeholder="Task"
            />
            <input
              value={item.assignee || ""}
              onChange={(e) => updateItem(index, "assignee", e.target.value)}
              placeholder="Assignee"
            />
            <input
              value={item.deadline || ""}
              onChange={(e) => updateItem(index, "deadline", e.target.value)}
              placeholder="Deadline"
            />
          </div>
        ))}
      </div>
      <button type="button" className="sma-btn-save" onClick={onSave}>
        Save Tasks
      </button>
    </section>
  );
}
