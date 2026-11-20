import { spawn } from "node:child_process";
import { chmodSync, readFileSync, rmSync } from "node:fs";
import { createConnection, createServer } from "node:net";
import { dirname, join } from "node:path";

const [mode, socketPath, deploymentId, localPort] = process.argv.slice(2);
const deploymentPattern = /^cbio-mcp-[a-f0-9]{12}$/;
const deploymentIdLength = "cbio-mcp-000000000000".length;

function pair(left, right) {
  left.on("error", () => left.destroy());
  right.on("error", () => right.destroy());
  left.on("close", (hadError) => {
    if (hadError || !left.readableEnded) right.destroy();
  });
  right.on("close", (hadError) => {
    if (hadError || !right.readableEnded) left.destroy();
  });
  left.pipe(right);
  right.pipe(left);
}

function listenUnix(server, path) {
  rmSync(path, { force: true });
  server.listen(path, () => chmodSync(path, 0o600));
}

function portalProxy(socket) {
  // Route only to a ready portal owned by this MCP. The client supplies an ID,
  // so the socket cannot be used as a general proxy into the host network.
  const readId = () => {
    const rawId = socket.read(deploymentIdLength);
    if (!rawId) return;
    socket.off("readable", readId);
    try {
      const id = rawId.toString("ascii");
      if (!deploymentPattern.test(id)) throw new Error("Invalid deployment ID");
      const state = JSON.parse(readFileSync(join(process.env.CBIO_MCP_HOME, id, "state.json")));
      if (state.id !== id || state.phase !== "ready"
          || !Number.isInteger(state.port) || state.port < 1024 || state.port > 65535) {
        throw new Error("Deployment is not ready");
      }
      socket.setTimeout(0);
      pair(socket, createConnection({ host: "127.0.0.1", port: state.port, allowHalfOpen: true }));
    } catch {
      socket.destroy();
    }
  };
  socket.on("error", () => socket.destroy());
  socket.setTimeout(5000, () => socket.destroy());
  socket.on("readable", readId);
}

if (mode === "client") {
  // Docker may restart Engineer before the sidecar after a host reboot.
  const deadline = Date.now() + 30_000;
  const connect = () => {
    const socket = createConnection(socketPath);
    let connected = false;
    socket.on("connect", () => {
      connected = true;
      process.stdin.pipe(socket);
      socket.pipe(process.stdout);
    });
    socket.on("error", (error) => {
      if (!connected && Date.now() < deadline
          && ["ENOENT", "ECONNREFUSED"].includes(error.code)) {
        setTimeout(connect, 500);
      } else {
        console.error(error.message);
        process.exitCode = 1;
      }
    });
    socket.on("close", () => process.stdin.pause());
  };
  connect();
} else if (mode === "portal-client") {
  const port = Number(localPort);
  if (!deploymentPattern.test(deploymentId)
      || !Number.isInteger(port) || port < 1024 || port > 65535) {
    throw new Error("Expected a deployment ID and local port");
  }
  createServer({ allowHalfOpen: true }, (socket) => {
    const upstream = createConnection({ path: socketPath, allowHalfOpen: true });
    upstream.write(deploymentId);
    pair(socket, upstream);
  }).listen(port, "127.0.0.1");
} else if (mode === "server") {
  // The MCP has one persistent state directory and expects a single server.
  let child;
  const server = createServer({ allowHalfOpen: true }, (socket) => {
    socket.on("error", () => socket.destroy());
    if (child) {
      socket.destroy();
      return;
    }
    const worker = spawn("bun", ["/app/src/server.ts"], {
      stdio: ["pipe", "pipe", "inherit"],
    });
    child = worker;
    worker.stdin.on("error", () => socket.destroy());
    worker.on("error", (error) => {
      console.error(error.message);
      socket.destroy();
    });
    worker.on("close", () => {
      child = undefined;
      socket.end();
    });
    socket.on("close", () => worker.kill());
    socket.pipe(worker.stdin);
    worker.stdout.pipe(socket, { end: false });
  });
  listenUnix(server, socketPath);
  listenUnix(createServer({ allowHalfOpen: true }, portalProxy), join(dirname(socketPath), "portal.sock"));
} else {
  throw new Error("Expected client or server and a Unix socket path");
}
