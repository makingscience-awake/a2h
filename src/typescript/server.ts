import { createServer, type IncomingMessage, type ServerResponse, type Server } from "node:http";
import { Gateway } from "./gateway.js";
import type { Priority, ResponseType } from "./models.js";
import { A2HError, ParticipantNotFound, SenderNotRegistered } from "./errors.js";

function sendJson(res: ServerResponse, status: number, data: unknown): void {
  const body = JSON.stringify(data);
  res.writeHead(status, { "Content-Type": "application/json", "Content-Length": Buffer.byteLength(body) });
  res.end(body);
}

function parseBody(req: IncomingMessage): Promise<Record<string, unknown>> {
  return new Promise((resolve, reject) => {
    const chunks: Buffer[] = [];
    req.on("data", (chunk: Buffer) => chunks.push(chunk));
    req.on("end", () => {
      try {
        const text = Buffer.concat(chunks).toString("utf-8");
        resolve(text ? JSON.parse(text) : {});
      } catch (err) {
        reject(err);
      }
    });
    req.on("error", reject);
  });
}

function errorStatus(err: A2HError): number {
  if (err instanceof ParticipantNotFound) return 404;
  if (err instanceof SenderNotRegistered) return 403;
  return 400;
}

export function createA2HServer(
  gateway: Gateway,
  port = 8080
): { start(): Promise<void>; stop(): Promise<void> } {
  let server: Server;

  async function handler(req: IncomingMessage, res: ServerResponse): Promise<void> {
    const url = new URL(req.url ?? "/", `http://localhost:${port}`);
    const method = req.method ?? "GET";
    const path = url.pathname;

    try {
      // POST /a2h/v1/requests
      if (method === "POST" && path === "/a2h/v1/requests") {
        const body = await parseBody(req);
        const ix = await gateway.ask(body.to as string, {
          question: (body.question as string) ?? "",
          responseType: body.response_type as ResponseType | undefined,
          options: body.options as Array<{ label: string; value: string; description?: string }> | undefined,
          context: body.context as Record<string, unknown> | undefined,
          priority: body.priority as Priority | undefined,
          deadline: body.deadline as string | undefined,
          slaHours: body.sla_hours as number | undefined,
          fromParticipant: (body.from_participant as string) ?? undefined,
        });
        sendJson(res, 201, { id: ix.id, status: ix.status, deadline: ix.deadline });
        return;
      }

      // GET /a2h/v1/requests?to=...
      if (method === "GET" && path === "/a2h/v1/requests") {
        const to = url.searchParams.get("to") ?? undefined;
        const list = gateway.listPending(to);
        sendJson(res, 200, { requests: list.map((ix) => ix.toDict()) });
        return;
      }

      // GET /a2h/v1/requests/:id
      const getMatch = path.match(/^\/a2h\/v1\/requests\/([^/]+)$/);
      if (method === "GET" && getMatch) {
        const ix = gateway.get(getMatch[1]!);
        if (!ix) { sendJson(res, 404, { error: "not_found" }); return; }
        sendJson(res, 200, ix.toDict());
        return;
      }

      // POST /a2h/v1/requests/:id/respond
      const respondMatch = path.match(/^\/a2h\/v1\/requests\/([^/]+)\/respond$/);
      if (method === "POST" && respondMatch) {
        const body = await parseBody(req);
        const result = gateway.respond(
          respondMatch[1]!,
          (body.response as Record<string, unknown>) ?? body,
          (body.channel as string) ?? "dashboard"
        );
        sendJson(res, result.success ? 200 : 400, { success: result.success, request_id: respondMatch[1], status: result.status });
        return;
      }

      // POST /a2h/v1/requests/:id/cancel
      const cancelMatch = path.match(/^\/a2h\/v1\/requests\/([^/]+)\/cancel$/);
      if (method === "POST" && cancelMatch) {
        const body = await parseBody(req);
        const result = gateway.cancel(cancelMatch[1]!, (body.reason as string) ?? "");
        sendJson(res, result.success ? 200 : 400, { success: result.success, request_id: cancelMatch[1], status: result.status });
        return;
      }

      // POST /a2h/v1/notifications
      if (method === "POST" && path === "/a2h/v1/notifications") {
        const body = await parseBody(req);
        const notif = await gateway.notify(body.to as string, {
          message: (body.message as string) ?? "",
          severity: body.severity as string | undefined,
          priority: body.priority as Priority | undefined,
          context: body.context as Record<string, unknown> | undefined,
          fromParticipant: body.from_participant as string | undefined,
        });
        sendJson(res, 201, { id: notif.id, delivered: true });
        return;
      }

      // GET /.well-known/participants.json
      if (method === "GET" && path === "/.well-known/participants.json") {
        sendJson(res, 200, gateway.discover());
        return;
      }

      sendJson(res, 404, { error: "not_found", message: `${method} ${path} not found` });
    } catch (err) {
      if (err instanceof A2HError) {
        sendJson(res, errorStatus(err), err.toDict());
      } else {
        sendJson(res, 500, { error: "internal", message: String(err) });
      }
    }
  }

  return {
    start(): Promise<void> {
      return new Promise((resolve) => {
        server = createServer((req, res) => { void handler(req, res); });
        server.listen(port, () => resolve());
      });
    },
    stop(): Promise<void> {
      return new Promise((resolve, reject) => {
        if (!server) { resolve(); return; }
        server.close((err) => (err ? reject(err) : resolve()));
      });
    },
  };
}
