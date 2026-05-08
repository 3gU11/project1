require('dotenv').config();
const express = require('express');
const cors = require('cors');
const http = require('http');
const { Server } = require('socket.io');
const { WebSocketServer, WebSocket } = require('ws');

const db = require('./db');
const { initRedis } = require('./redis');

// Routes
const authRoutes = require('./routes/auth');
const batchRoutes = require('./routes/batches');
const unitRoutes = require('./routes/units');
const lineRoutes = require('./routes/productionLines');
const configRoutes = require('./routes/config');
const forecastRoutes = require('./routes/forecast');
const queueRoutes = require('./routes/queue');

const app = express();
const server = http.createServer(app);
const io = new Server(server, {
  cors: { origin: '*', methods: ['GET', 'POST', 'PATCH', 'DELETE'] }
});
const rawWss = new WebSocketServer({ noServer: true });

function emitRealtime(event, data) {
  io.emit(event, data);

  const payload = JSON.stringify({ event, data });
  rawWss.clients.forEach((client) => {
    if (client.readyState === WebSocket.OPEN) {
      client.send(payload);
    }
  });
}

// Middleware
app.use(cors());
app.use(express.json());

// Keep route API unchanged while broadcasting to both socket.io and native /ws clients.
app.set('io', { emit: emitRealtime });

// Routes
app.use('/api/auth', authRoutes);
app.use('/api/batches', batchRoutes);
app.use('/api/units', unitRoutes);
app.use('/api/production-lines', lineRoutes);
app.use('/api', configRoutes);
app.use('/api/forecast', forecastRoutes);
app.use('/api/production-queue', queueRoutes);

// Health check
app.get('/api/health', (req, res) => res.json({ status: 'ok', version: '2.2.0' }));

// WebSocket
io.on('connection', (socket) => {
  console.log(`WS connected: ${socket.id}`);
  socket.on('disconnect', () => console.log(`WS disconnected: ${socket.id}`));
});

server.on('upgrade', (request, socket, head) => {
  const reqPath = String(request.url || '');
  if (!reqPath.startsWith('/ws')) return;

  rawWss.handleUpgrade(request, socket, head, (ws) => {
    rawWss.emit('connection', ws, request);
  });
});

rawWss.on('connection', (ws) => {
  console.log('Native WS connected');
  ws.on('error', () => {});
  ws.on('close', () => console.log('Native WS disconnected'));
});

const PORT = process.env.PORT || 3001;

async function start() {
  try {
    await db.query('SELECT 1');
    console.log('MySQL connected');
    const redisClient = await initRedis();
    console.log(redisClient ? 'Redis connected' : 'Redis disabled, using in-memory locks');

    server.listen(PORT, () => {
      console.log(`Server running on http://localhost:${PORT}`);
    });
  } catch (err) {
    console.error('Startup failed:', err.message);
    process.exit(1);
  }
}

start();

module.exports = { app, io };
