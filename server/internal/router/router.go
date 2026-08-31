package router

import (
	"github.com/gin-gonic/gin"
	"gorm.io/gorm"

	"smart-scheduling/server/internal/handler"
	"smart-scheduling/server/internal/middleware"
	"smart-scheduling/server/internal/ws"
)

func Setup(r *gin.Engine, db *gorm.DB, hub *ws.Hub,
	bh *handler.BatchHandler,
	uh *handler.UnitHandler,
	fh *handler.ForecastHandler,
	lh *handler.LineHandler,
	ch *handler.CapacityHandler,
	ah *handler.AuthHandler,
	mh *handler.MetaHandler,
	qh *handler.QueueHandler,
	ph *handler.PhotoHandler,
	allowOrigins string,
) {
	r.Use(middleware.CORS(allowOrigins))

	// WebSocket
	r.GET("/ws", func(c *gin.Context) { hub.ServeWS(c.Writer, c.Request) })

	api := r.Group("/api")
	api.GET("/health", func(c *gin.Context) { c.JSON(200, gin.H{"status": "ok", "version": "go"}) })
	api.POST("/auth/login", ah.Login)
	api.GET("/auth/me", middleware.AuthMiddleware(db), ah.Me)
	api.GET("/model-types", middleware.AdminOnly(db), mh.ModelTypes)
	api.POST("/units/:id/notify-update", uh.NotifyUpdate)

	v1 := r.Group("/api/v1")
	v1.POST("/auth/login", ah.Login)
	v1.GET("/auth/me", middleware.AuthMiddleware(db), ah.Me)
	v1.GET("/model-types", middleware.AuthMiddleware(db), mh.ModelTypes)
	v1.GET("/photo-files/:fileId/download", middleware.AuthMiddleware(db), ph.DownloadTaskPhoto)

	v1Auth := v1.Group("")
	v1Auth.Use(middleware.AuthMiddleware(db))
	{
		v1Auth.GET("/machines/:serialNo/photo-profile", ph.MachinePhotoProfile)
		v1Auth.POST("/machines/:serialNo/photo-tasks/init", ph.InitMachinePhotoTasks)
		v1Auth.GET("/machines/:serialNo/photo-tasks", ph.MachinePhotoTasks)
		v1Auth.POST("/photo-tasks/:taskId/upload", ph.UploadTaskPhoto)
		v1Auth.DELETE("/photo-tasks/:taskId/photo", ph.DeleteTaskPhoto)
		v1Auth.POST("/photo-tasks/:taskId/qr-decode", ph.DecodeTaskQR)
		v1Auth.POST("/photo-tasks/:taskId/ocr", ph.RunTaskOCR)
		v1Auth.POST("/photo-tasks/:taskId/recognition", ph.SaveTaskRecognition)
		v1Auth.POST("/photo-tasks/:taskId/confirm", ph.ConfirmTaskOCR)
		v1Auth.POST("/machines/:serialNo/photo-submit", ph.SubmitMachinePhotos)
		v1Auth.GET("/model-dictionary/", ph.ListModelDictionary)
	}

	v1Admin := v1.Group("")
	v1Admin.Use(middleware.AdminOnly(db))
	{
		v1Admin.POST("/model-dictionary/save", ph.SaveModelDictionary)
		v1Admin.GET("/model-dictionary/:modelId/photo-config", ph.GetModelPhotoConfig)
		v1Admin.POST("/model-dictionary/:modelId/photo-config/save", ph.SaveModelPhotoConfig)
		v1Admin.GET("/model-dictionary/photo-config/import-template", ph.DownloadPhotoImportTemplate)
		v1Admin.POST("/model-dictionary/photo-config/import", ph.ImportModelPhotoConfig)
		v1Admin.GET("/photo-items", ph.ListPhotoItems)
		v1Admin.POST("/photo-items/save", ph.SavePhotoItems)
		v1Admin.GET("/ocr-field-rules", ph.ListOCRFieldRules)
		v1Admin.POST("/ocr-field-rules/save", ph.SaveOCRFieldRules)
	}

	api.Use(middleware.AdminOnly(db))
	{
		// Batches
		api.GET("/batches", bh.List)
		api.GET("/batches/:id", bh.GetByID)
		api.GET("/batches/:id/units", bh.GetBatchUnits)
		api.POST("/batches/manual-predicted", bh.CreateManualPredicted)
		api.POST("/batches/:id/confirm", bh.Confirm)
		api.POST("/batches/:id/revoke", bh.Revoke)
		api.POST("/batches/batch-confirm", bh.BatchConfirm)
		api.POST("/batches/:id/insert-empty-slot", bh.InsertEmptySlot)
		api.PATCH("/batches/:id/stock-models", bh.SyncStockModels)

		// Production Queue - 查询 production_queue 表中溢出的待处理订单
		api.GET("/production-queue", qh.List)

		// Units
		api.GET("/units/empty-containers", uh.EmptyContainers)
		api.POST("/units/special-card", uh.CreateSpecialCard)
		api.GET("/units/:id", uh.GetByID)
		api.PATCH("/units/:id", uh.Update)
		api.PATCH("/units/:id/unlock", uh.Unlock)
		api.POST("/units/:id/move-batch", uh.MoveBatch)
		api.POST("/units/:id/move-to-special", uh.MoveToSpecial)
		api.POST("/units/:id/reorder-slot", uh.ReorderSlot)
		api.POST("/units/repair-family-mismatches", uh.RepairFamilyMismatches)
		api.POST("/units/swap-content", uh.SwapContent)
		api.POST("/units/rush-insert", uh.RushInsert)
		api.POST("/units/:id/convert-to-rush", uh.ConvertToRush)
		api.POST("/units/:id/mark-spot", uh.MarkSpot)

		// Forecast
		api.POST("/forecast/recompute", fh.Recompute)
		api.GET("/forecast/achievement", fh.Achievement)

		// Capacity config
		api.GET("/capacity-ratio", ch.Get)
		api.PATCH("/capacity-ratio", ch.Update)

		// Production lines
		api.GET("/production-lines", lh.List)
		api.POST("/production-lines/reconcile-inbound", lh.ReconcileInbound)
		api.POST("/production-lines/:id/assign", lh.Assign)
		api.POST("/production-lines/:id/manual-complete", lh.ManualComplete)
		api.POST("/production-lines/:id/lock-units", lh.LockUnits)
	}
}
