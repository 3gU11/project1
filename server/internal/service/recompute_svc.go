package service

import (
	"context"
	"fmt"
	"time"

	"smart-scheduling/server/internal/engine"
	"smart-scheduling/server/internal/lock"
	"smart-scheduling/server/internal/ws"
)

type RecomputeSvc struct {
	lockMgr   *lock.Manager
	predictor *engine.Predictor
	wsHub     *ws.Hub
}

func NewRecomputeSvc(lm *lock.Manager, p *engine.Predictor, hub *ws.Hub) *RecomputeSvc {
	return &RecomputeSvc{lockMgr: lm, predictor: p, wsHub: hub}
}

func (s *RecomputeSvc) Recompute(targetSlotNo int) (interface{}, error) {
	if targetSlotNo <= 0 {
		targetSlotNo = 1
	}
	unlock, err := s.lockMgr.Acquire(context.Background(), "lock:recompute", 60*time.Second)
	if err != nil {
		if err == lock.ErrLocked {
			return nil, fmt.Errorf("recompute already in progress")
		}
		return nil, fmt.Errorf("acquire lock: %w", err)
	}
	defer unlock()

	batches, err := s.predictor.FullRecompute(targetSlotNo)
	if err != nil {
		return nil, fmt.Errorf("recompute: %w", err)
	}

	s.wsHub.Broadcast("batch:updated", map[string]interface{}{
		"count": len(batches),
	})

	return map[string]interface{}{
		"batches":        batches,
		"count":          len(batches),
		"target_slot_no": targetSlotNo,
	}, nil
}
