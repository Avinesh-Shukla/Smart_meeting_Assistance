const http = require("http");
const nodemailer = require("nodemailer");

// Configuration from environment
const PORT = process.env.EMAIL_SERVICE_PORT || 3001;
const SMTP_HOST = process.env.SMTP_HOST || "";
const SMTP_PORT = parseInt(process.env.SMTP_PORT || "587", 10);
const SMTP_USERNAME = process.env.SMTP_USERNAME || "";
const SMTP_PASSWORD = process.env.SMTP_PASSWORD || "";
const SMTP_FROM = process.env.SMTP_SENDER || "";
const SMTP_USE_TLS = process.env.SMTP_USE_TLS !== "false";

let transporter = null;

function initializeTransporter() {
  if (!SMTP_HOST || !SMTP_USERNAME || !SMTP_PASSWORD) {
    console.warn(
      "⚠️  SMTP credentials not configured. Email sending will fail."
    );
    console.warn("Set SMTP_HOST, SMTP_USERNAME, SMTP_PASSWORD in .env");
    return null;
  }

  transporter = nodemailer.createTransport({
    host: SMTP_HOST,
    port: SMTP_PORT,
    secure: SMTP_PORT === 465,
    auth: {
      user: SMTP_USERNAME,
      pass: SMTP_PASSWORD,
    },
    tls: {
      rejectUnauthorized: false, // For self-signed certs
    },
  });

  console.log(`📧 Email service ready: ${SMTP_USERNAME}@${SMTP_HOST}:${SMTP_PORT}`);
  return transporter;
}

async function sendEmail(to, subject, text, html = null) {
  if (!transporter) {
    throw new Error("Email service not initialized. Check SMTP config.");
  }

  return new Promise((resolve, reject) => {
    const mailOptions = {
      from: SMTP_FROM,
      to,
      subject,
      text,
      ...(html && { html }),
    };

    transporter.sendMail(mailOptions, (error, info) => {
      if (error) {
        console.error(`❌ Email send failed (to=${to}):`, error.message);
        reject(error);
      } else {
        console.log(`✅ Email sent to ${to}: ${info.messageId}`);
        resolve(info);
      }
    });
  });
}

const server = http.createServer(async (req, res) => {
  // CORS headers
  res.setHeader("Access-Control-Allow-Origin", "*");
  res.setHeader("Access-Control-Allow-Methods", "GET, POST, OPTIONS");
  res.setHeader("Access-Control-Allow-Headers", "Content-Type");
  res.setHeader("Content-Type", "application/json");

  if (req.method === "OPTIONS") {
    res.writeHead(200);
    res.end();
    return;
  }

  if (req.method === "GET" && req.url === "/health") {
    res.writeHead(200);
    res.end(
      JSON.stringify({
        status: "ok",
        service: "email-service",
        smtp_configured: SMTP_HOST !== "",
      })
    );
    return;
  }

  if (req.method === "POST" && req.url === "/send") {
    let body = "";

    req.on("data", (chunk) => {
      body += chunk.toString();
    });

    req.on("end", async () => {
      try {
        const data = JSON.parse(body);
        const { to, subject, text, html } = data;

        if (!to || !subject || !text) {
          res.writeHead(400);
          res.end(
            JSON.stringify({
              ok: false,
              error: "Missing required fields: to, subject, text",
            })
          );
          return;
        }

        const info = await sendEmail(to, subject, text, html);
        res.writeHead(200);
        res.end(
          JSON.stringify({
            ok: true,
            message_id: info.messageId,
            response: info.response,
          })
        );
      } catch (error) {
        console.error("Request error:", error);
        res.writeHead(500);
        res.end(
          JSON.stringify({
            ok: false,
            error: error.message || "Email send failed",
          })
        );
      }
    });
    return;
  }

  // 404
  res.writeHead(404);
  res.end(JSON.stringify({ ok: false, error: "Not found" }));
});

// Initialize and start
initializeTransporter();

server.listen(PORT, "127.0.0.1", () => {
  console.log(`\n🚀 Email Service running on http://127.0.0.1:${PORT}`);
  console.log("   POST /send - Send email");
  console.log("   GET /health - Health check\n");
});

// Graceful shutdown
process.on("SIGTERM", () => {
  server.close(() => {
    console.log("\n📧 Email service closed.");
    process.exit(0);
  });
});
