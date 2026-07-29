package main

import (
	"fmt"
	"log"
	"time"

	"github.com/gin-gonic/gin"

	"smart-scheduling/server/internal/config"
	"smart-scheduling/server/internal/database"
	"smart-scheduling/server/internal/engine"
	"smart-scheduling/server/internal/handler"
	"smart-scheduling/server/internal/lock"
	"smart-scheduling/server/internal/repo"
	"smart-scheduling/server/internal/router"
	"smart-scheduling/server/internal/service"
	"smart-scheduling/server/internal/ws"
)

func main() {
	cfg := config.Load()
	fmt.Printf("Starting server on %s\n", cfg.HTTPAddr)

	db, err := database.OpenMySQL(cfg)
	if err != nil {
		log.Fatalf("failed to connect database: %v", err)
	}

	rdb := database.OpenRedis(cfg)
	if rdb == nil {
		log.Println("Redis disabled or unavailable; using local in-process locks")
	} else {
		log.Printf("Redis connected: %s", cfg.RedisAddr)
	}

	lockMgr := lock.NewManager(rdb)
	hub := ws.NewHub()

	batchRepo := repo.NewBatchRepo(db)
	unitRepo := repo.NewUnitRepo(db)
	configRepo := repo.NewConfigRepo(db)

	batchSvc := service.NewBatchSvc(db, batchRepo, unitRepo, configRepo, hub)
	if completed, reconcileErr := batchSvc.ReconcileInboundBatches(nil, "system-startup"); reconcileErr != nil {
		log.Printf("startup inbound reconciliation failed: %v", reconcileErr)
	} else if len(completed) > 0 {
		log.Printf("startup inbound reconciliation completed %d batches", len(completed))
	}
	go func() {
		ticker := time.NewTicker(time.Minute)
		defer ticker.Stop()
		for range ticker.C {
			completed, reconcileErr := batchSvc.ReconcileInboundBatches(nil, "system-periodic")
			if reconcileErr != nil {
				log.Printf("periodic inbound reconciliation failed: %v", reconcileErr)
			} else if len(completed) > 0 {
				log.Printf("periodic inbound reconciliation completed %d batches", len(completed))
			}
		}
	}()
	rushSvc := service.NewRushSvc(db, unitRepo, batchRepo, hub)
	predictor := engine.NewPredictor(db, batchRepo, unitRepo, configRepo)
	recomputeSvc := service.NewRecomputeSvc(lockMgr, predictor, hub)

	bh := handler.NewBatchHandler(db, batchRepo, unitRepo, batchSvc)
	uh := handler.NewUnitHandler(db, unitRepo, batchRepo, rushSvc, cfg.PythonURL, cfg.InternalToken, hub)
	fh := handler.NewForecastHandler(db, recomputeSvc)
	lh := handler.NewLineHandler(db, batchSvc)
	ch := handler.NewCapacityHandler(db, configRepo)
	ah := handler.NewAuthHandler(db)
	mh := handler.NewMetaHandler(db)
	qh := handler.NewQueueHandler(db)
	ph := handler.NewPhotoHandler(db, cfg.OCREnabled, cfg.OCRServiceURL, cfg.OCRTimeoutMS)

	r := gin.Default()
	router.Setup(r, db, hub, bh, uh, fh, lh, ch, ah, mh, qh, ph, cfg.AllowOrigins)

	log.Printf("Listening on %s", cfg.HTTPAddr)
	if err := r.Run(cfg.HTTPAddr); err != nil {
		log.Fatalf("server error: %v", err)
	}
}
