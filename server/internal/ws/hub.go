package ws

import (
	"encoding/json"
	"log"
	"net/http"
	"sync"
	"time"

	"github.com/gorilla/websocket"
)

var upgrader = websocket.Upgrader{
	CheckOrigin: func(r *http.Request) bool { return true },
	HandshakeTimeout: 10 * time.Second,
}

type Client struct {
	conn *websocket.Conn
	send chan []byte
}

type Message struct {
	Event string      `json:"event"`
	Data  interface{} `json:"data"`
}

type Hub struct {
	mu       sync.RWMutex
	clients  map[*Client]bool
	register chan *Client
	unreg    chan *Client
}

func NewHub() *Hub {
	h := &Hub{
		clients:  make(map[*Client]bool),
		register: make(chan *Client, 32),
		unreg:    make(chan *Client, 32),
	}
	go h.run()
	return h
}

func (h *Hub) run() {
	for {
		select {
		case c := <-h.register:
			h.mu.Lock()
			h.clients[c] = true
			h.mu.Unlock()
		case c := <-h.unreg:
			h.mu.Lock()
			if _, ok := h.clients[c]; ok {
				delete(h.clients, c)
				close(c.send)
			}
			h.mu.Unlock()
		}
	}
}

func (h *Hub) ServeWS(w http.ResponseWriter, r *http.Request) {
	conn, err := upgrader.Upgrade(w, r, nil)
	if err != nil {
		log.Printf("ws upgrade: %v", err)
		return
	}
	c := &Client{conn: conn, send: make(chan []byte, 64)}
	h.register <- c

	go c.writeLoop()
	go c.readLoop(h)
}

func (h *Hub) Broadcast(event string, data interface{}) {
	msg, err := json.Marshal(Message{Event: event, Data: data})
	if err != nil {
		log.Printf("ws marshal: %v", err)
		return
	}
	h.mu.RLock()
	defer h.mu.RUnlock()
	for c := range h.clients {
		select {
		case c.send <- msg:
		default:
		}
	}
}

func (c *Client) writeLoop() {
	defer c.conn.Close()
	for msg := range c.send {
		if err := c.conn.WriteMessage(websocket.TextMessage, msg); err != nil {
			return
		}
	}
}

func (c *Client) readLoop(h *Hub) {
	defer func() {
		h.unreg <- c
		c.conn.Close()
	}()
	c.conn.SetReadLimit(4096)
	for {
		_, _, err := c.conn.ReadMessage()
		if err != nil {
			break
		}
	}
}
