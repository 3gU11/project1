package lock

import (
	"context"
	"errors"
	"sync"
	"time"

	"github.com/go-redis/redis/v8"
)

var ErrLocked = errors.New("resource locked")

type Manager struct {
	rdb      *redis.Client
	localMu  sync.Mutex
	localKey map[string]time.Time
}

func NewManager(rdb *redis.Client) *Manager {
	return &Manager{rdb: rdb, localKey: map[string]time.Time{}}
}

func (m *Manager) Acquire(ctx context.Context, key string, ttl time.Duration) (func(), error) {
	if m.rdb != nil {
		token := time.Now().Format(time.RFC3339Nano)
		ok, err := m.rdb.SetNX(ctx, key, token, ttl).Result()
		if err == nil {
			if !ok {
				return nil, ErrLocked
			}
			return func() { _ = m.rdb.Del(context.Background(), key).Err() }, nil
		}
	}

	if !m.localMu.TryLock() {
		return nil, ErrLocked
	}
	m.localKey[key] = time.Now().Add(ttl)
	return func() {
		delete(m.localKey, key)
		m.localMu.Unlock()
	}, nil
}
