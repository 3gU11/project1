package handler

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"mime/multipart"
	"net/http"
	"os"
	"path/filepath"
	"regexp"
	"strconv"
	"strings"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/xuri/excelize/v2"
	"gorm.io/gorm"
)

type PhotoHandler struct {
	db            *gorm.DB
	ocrEnabled    bool
	ocrServiceURL string
	qrServiceURL  string
	internalToken string
	ocrTimeout    time.Duration
}

func NewPhotoHandler(db *gorm.DB, ocrEnabled bool, ocrServiceURL string, qrServiceURL string, internalToken string, ocrTimeoutMS int) *PhotoHandler {
	if ocrTimeoutMS <= 0 {
		ocrTimeoutMS = 20000
	}
	return &PhotoHandler{
		db:            db,
		ocrEnabled:    ocrEnabled,
		ocrServiceURL: strings.TrimSpace(ocrServiceURL),
		qrServiceURL:  strings.TrimSpace(qrServiceURL),
		internalToken: strings.TrimSpace(internalToken),
		ocrTimeout:    time.Duration(ocrTimeoutMS) * time.Millisecond,
	}
}

type photoItemRow struct {
	ID                  int64  `json:"id" gorm:"column:id"`
	PositionCode        string `json:"position_code" gorm:"column:position_code"`
	ItemName            string `json:"item_name" gorm:"column:item_name"`
	ItemCategory        string `json:"item_category" gorm:"column:item_category"`
	ShootingRequirement string `json:"shooting_requirement" gorm:"column:shooting_requirement"`
	DefaultRequired     bool   `json:"default_required" gorm:"column:default_required"`
	DefaultOCREnabled   bool   `json:"default_ocr_enabled" gorm:"column:default_ocr_enabled"`
	DefaultOCRProfile   string `json:"default_ocr_profile" gorm:"column:default_ocr_profile"`
	SortOrder           int    `json:"sort_order" gorm:"column:sort_order"`
	Enabled             bool   `json:"enabled" gorm:"column:enabled"`
}

type modelPhotoConfigRow struct {
	ID                  int64  `json:"id" gorm:"column:id"`
	ModelID             int64  `json:"model_id" gorm:"column:model_id"`
	ModelName           string `json:"model_name" gorm:"column:model_name"`
	PositionCode        string `json:"position_code" gorm:"column:position_code"`
	ItemName            string `json:"item_name" gorm:"column:item_name"`
	ItemCategory        string `json:"item_category" gorm:"column:item_category"`
	ShootingRequirement string `json:"shooting_requirement" gorm:"column:shooting_requirement"`
	Required            bool   `json:"required" gorm:"column:required"`
	OCREnabled          bool   `json:"ocr_enabled" gorm:"column:ocr_enabled"`
	OCRProfile          string `json:"ocr_profile" gorm:"column:ocr_profile"`
	SortOrder           int    `json:"sort_order" gorm:"column:sort_order"`
	Enabled             bool   `json:"enabled" gorm:"column:enabled"`
	Remark              string `json:"remark" gorm:"column:remark"`
}

type ocrFieldRuleRow struct {
	ID                  int64   `json:"id" gorm:"column:id"`
	OCRProfile          string  `json:"ocr_profile" gorm:"column:ocr_profile"`
	PositionCode        string  `json:"position_code" gorm:"column:position_code"`
	FieldCode           string  `json:"field_code" gorm:"column:field_code"`
	FieldName           string  `json:"field_name" gorm:"column:field_name"`
	Required            bool    `json:"required" gorm:"column:required"`
	Pattern             string  `json:"pattern" gorm:"column:pattern"`
	ConfidenceThreshold float64 `json:"confidence_threshold" gorm:"column:confidence_threshold"`
	CompareTarget       string  `json:"compare_target" gorm:"column:compare_target"`
	Enabled             bool    `json:"enabled" gorm:"column:enabled"`
}

type machinePhotoTaskRow struct {
	ID           int64          `json:"id" gorm:"column:id"`
	SerialNo     string         `json:"serial_no" gorm:"column:serial_no"`
	ModelName    string         `json:"model_name" gorm:"column:model_name"`
	PositionCode string         `json:"position_code" gorm:"column:position_code"`
	ItemName     string         `json:"item_name" gorm:"column:item_name"`
	Required     bool           `json:"required" gorm:"column:required"`
	OCREnabled   bool           `json:"ocr_enabled" gorm:"column:ocr_enabled"`
	OCRProfile   string         `json:"ocr_profile" gorm:"column:ocr_profile"`
	Status       string         `json:"status" gorm:"column:status"`
	SortOrder    int            `json:"sort_order" gorm:"column:sort_order"`
	Enabled      bool           `json:"enabled" gorm:"column:enabled"`
	FileID       *int64         `json:"file_id" gorm:"column:file_id"`
	FileName     string         `json:"file_name" gorm:"column:file_name"`
	UploadedAt   string         `json:"uploaded_at" gorm:"column:uploaded_at"`
	OCRIssues    int            `json:"ocr_issues" gorm:"column:ocr_issues"`
	OCRResults   []ocrResultRow `json:"ocr_results" gorm:"-"`
}

type ocrResultRow struct {
	ID                int64   `json:"id" gorm:"column:id"`
	TaskID            int64   `json:"task_id" gorm:"column:task_id"`
	FieldCode         string  `json:"field_code" gorm:"column:field_code"`
	FieldName         string  `json:"field_name" gorm:"column:field_name"`
	RecognizedValue   string  `json:"recognized_value" gorm:"column:recognized_value"`
	ManualValue       string  `json:"manual_value" gorm:"column:manual_value"`
	DisplayValue      string  `json:"display_value" gorm:"column:display_value"`
	Confidence        float64 `json:"confidence" gorm:"column:confidence"`
	CheckStatus       string  `json:"check_status" gorm:"column:check_status"`
	RecognitionSource string  `json:"recognition_source" gorm:"column:recognition_source"`
}

type machineProfileRow struct {
	BatchNo  string `json:"batch_no" gorm:"column:batch_no"`
	Model    string `json:"model" gorm:"column:model"`
	SerialNo string `json:"serial_no" gorm:"column:serial_no"`
	Status   string `json:"status" gorm:"column:status"`
	SlotCode string `json:"slot_code" gorm:"column:slot_code"`
}

type photoImportPayload struct {
	PhotoItems  []photoItemRow        `json:"photo_items"`
	ModelConfig []modelPhotoConfigRow `json:"model_config"`
	OCRRules    []ocrFieldRuleRow     `json:"ocr_rules"`
}

func (h *PhotoHandler) ListModelDictionary(c *gin.Context) {
	var rows []struct {
		ID          int64  `json:"id" gorm:"column:id"`
		ModelName   string `json:"model_name" gorm:"column:model_name"`
		ModelFamily string `json:"model_family" gorm:"column:model_family"`
		SortOrder   int    `json:"sort_order" gorm:"column:sort_order"`
		Enabled     bool   `json:"enabled" gorm:"column:enabled"`
		Remark      string `json:"remark" gorm:"column:remark"`
		UpdatedAt   string `json:"updated_at" gorm:"column:updated_at"`
	}
	if err := h.db.Table("model_dictionary").
		Select("id, model_name, COALESCE(model_family, '') AS model_family, sort_order, enabled, COALESCE(remark, '') AS remark, DATE_FORMAT(updated_at, '%Y-%m-%d %H:%i:%s') AS updated_at").
		Order("sort_order ASC, model_name ASC").
		Scan(&rows).Error; err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}
	c.JSON(http.StatusOK, gin.H{"data": rows})
}

func (h *PhotoHandler) SaveModelDictionary(c *gin.Context) {
	var req struct {
		Rows []struct {
			ID          *int64 `json:"id"`
			ModelName   string `json:"model_name"`
			ModelFamily string `json:"model_family"`
			SortOrder   int    `json:"sort_order"`
			Enabled     bool   `json:"enabled"`
			Remark      string `json:"remark"`
		} `json:"rows"`
	}
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "rows required"})
		return
	}
	seen := map[string]bool{}
	for i, row := range req.Rows {
		name := strings.TrimSpace(row.ModelName)
		if name == "" {
			c.JSON(http.StatusBadRequest, gin.H{"error": "机型名称不能为空"})
			return
		}
		key := strings.ToUpper(name)
		if seen[key] {
			c.JSON(http.StatusBadRequest, gin.H{"error": "机型名称不能重复: " + name})
			return
		}
		seen[key] = true
		req.Rows[i].SortOrder = i
	}

	tx := h.db.Begin()
	for _, row := range req.Rows {
		name := strings.TrimSpace(row.ModelName)
		updates := map[string]interface{}{
			"model_name":   name,
			"model_family": strings.TrimSpace(row.ModelFamily),
			"sort_order":   row.SortOrder,
			"enabled":      row.Enabled,
			"remark":       strings.TrimSpace(row.Remark),
			"updated_at":   time.Now(),
		}
		if row.ID != nil && *row.ID > 0 {
			if err := tx.Table("model_dictionary").Where("id = ?", *row.ID).Updates(updates).Error; err != nil {
				tx.Rollback()
				c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
				return
			}
			continue
		}
		if err := tx.Table("model_dictionary").Create(updates).Error; err != nil {
			tx.Rollback()
			c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
			return
		}
	}
	if err := tx.Commit().Error; err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}
	c.JSON(http.StatusOK, gin.H{"success": true})
}

func (h *PhotoHandler) ListPhotoItems(c *gin.Context) {
	var rows []photoItemRow
	if err := h.db.Table("photo_item_library").
		Order("sort_order ASC, position_code ASC").
		Scan(&rows).Error; err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}
	c.JSON(http.StatusOK, gin.H{"data": rows})
}

func (h *PhotoHandler) SavePhotoItems(c *gin.Context) {
	var req struct {
		Rows []photoItemRow `json:"rows"`
	}
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "rows required"})
		return
	}
	if err := h.savePhotoItemsRows(req.Rows); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}
	c.JSON(http.StatusOK, gin.H{"success": true})
}

func (h *PhotoHandler) GetModelPhotoConfig(c *gin.Context) {
	modelID, err := strconv.ParseInt(c.Param("modelId"), 10, 64)
	if err != nil || modelID <= 0 {
		c.JSON(http.StatusBadRequest, gin.H{"error": "invalid model id"})
		return
	}
	var rows []modelPhotoConfigRow
	if err := h.db.Raw(`
SELECT
  mpc.id,
  mpc.model_id,
  md.model_name,
  mpc.position_code,
  pil.item_name,
  COALESCE(pil.item_category, '') AS item_category,
  COALESCE(pil.shooting_requirement, '') AS shooting_requirement,
  mpc.required,
  mpc.ocr_enabled,
  COALESCE(mpc.ocr_profile, '') AS ocr_profile,
  mpc.sort_order,
  mpc.enabled,
  COALESCE(mpc.remark, '') AS remark
FROM model_photo_config mpc
JOIN model_dictionary md ON md.id = mpc.model_id
LEFT JOIN photo_item_library pil ON pil.position_code = mpc.position_code
WHERE mpc.model_id = ?
ORDER BY mpc.sort_order ASC, mpc.position_code ASC`, modelID).Scan(&rows).Error; err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}
	c.JSON(http.StatusOK, gin.H{"data": rows})
}

func (h *PhotoHandler) SaveModelPhotoConfig(c *gin.Context) {
	modelID, err := strconv.ParseInt(c.Param("modelId"), 10, 64)
	if err != nil || modelID <= 0 {
		c.JSON(http.StatusBadRequest, gin.H{"error": "invalid model id"})
		return
	}
	var req struct {
		Rows []modelPhotoConfigRow `json:"rows"`
	}
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "rows required"})
		return
	}
	if err := h.validateModelID(modelID); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}
	if err := h.replaceModelPhotoConfig(modelID, req.Rows, c.GetString("username")); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}
	c.JSON(http.StatusOK, gin.H{"success": true})
}

func (h *PhotoHandler) ImportModelPhotoConfig(c *gin.Context) {
	req, err := h.readPhotoImportPayload(c)
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}
	if err := h.applyPhotoImportPayload(req, c.GetString("username")); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}
	c.JSON(http.StatusOK, gin.H{"success": true})
}

func (h *PhotoHandler) DownloadPhotoImportTemplate(c *gin.Context) {
	file, err := buildPhotoImportTemplate()
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}
	defer file.Close()
	var buf bytes.Buffer
	if err := file.Write(&buf); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}
	c.Header("Content-Disposition", `attachment; filename="model_photo_config_template.xlsx"`)
	c.Data(http.StatusOK, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", buf.Bytes())
}

func (h *PhotoHandler) applyPhotoImportPayload(req photoImportPayload, actor string) error {
	if len(req.PhotoItems) > 0 {
		if err := h.savePhotoItemsRows(req.PhotoItems); err != nil {
			return err
		}
	}
	if len(req.OCRRules) > 0 {
		if err := h.saveOCRRules(req.OCRRules); err != nil {
			return err
		}
	}
	if len(req.ModelConfig) > 0 {
		grouped := map[int64][]modelPhotoConfigRow{}
		for _, row := range req.ModelConfig {
			modelID := row.ModelID
			if modelID == 0 && strings.TrimSpace(row.ModelName) != "" {
				resolvedID, err := h.modelIDByName(row.ModelName)
				if err != nil {
					return err
				}
				modelID = resolvedID
			}
			if modelID == 0 {
				return fmt.Errorf("机型配置必须提供 model_id 或 model_name")
			}
			grouped[modelID] = append(grouped[modelID], row)
		}
		for modelID, rows := range grouped {
			if err := h.replaceModelPhotoConfig(modelID, rows, actor); err != nil {
				return err
			}
		}
	}
	return nil
}

func (h *PhotoHandler) ListOCRFieldRules(c *gin.Context) {
	var rows []ocrFieldRuleRow
	if err := h.db.Table("ocr_field_rules").
		Order("ocr_profile ASC, position_code ASC, field_code ASC").
		Scan(&rows).Error; err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}
	c.JSON(http.StatusOK, gin.H{"data": rows})
}

func (h *PhotoHandler) SaveOCRFieldRules(c *gin.Context) {
	var req struct {
		Rows []ocrFieldRuleRow `json:"rows"`
	}
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "rows required"})
		return
	}
	if err := h.saveOCRRules(req.Rows); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}
	c.JSON(http.StatusOK, gin.H{"success": true})
}

func (h *PhotoHandler) MachinePhotoProfile(c *gin.Context) {
	serialNo := strings.TrimSpace(c.Param("serialNo"))
	profile, ok := h.loadMachineProfile(c, serialNo)
	if !ok {
		return
	}
	configRows, err := h.modelPhotoConfigByName(profile.Model)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}
	c.JSON(http.StatusOK, gin.H{
		"machine": profile,
		"config":  configRows,
	})
}

func (h *PhotoHandler) InitMachinePhotoTasks(c *gin.Context) {
	serialNo := strings.TrimSpace(c.Param("serialNo"))
	profile, ok := h.loadMachineProfile(c, serialNo)
	if !ok {
		return
	}
	configRows, err := h.modelPhotoConfigByName(profile.Model)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}
	if len(configRows) == 0 {
		c.JSON(http.StatusBadRequest, gin.H{"error": "该机型未维护拍照清单: " + profile.Model})
		return
	}
	tx := h.db.Begin()
	activeCodes := make([]string, 0, len(configRows))
	for _, cfg := range configRows {
		if cfg.Enabled {
			activeCodes = append(activeCodes, cfg.PositionCode)
		}
	}
	if len(activeCodes) > 0 {
		if err := tx.Table("machine_photo_tasks").
			Where("serial_no = ? AND position_code NOT IN ?", serialNo, activeCodes).
			Updates(map[string]interface{}{"enabled": false}).Error; err != nil {
			tx.Rollback()
			c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
			return
		}
		if err := tx.Table("machine_component_bindings").
			Where("machine_no = ? AND position_code NOT IN ?", serialNo, activeCodes).
			Updates(map[string]interface{}{"active": false}).Error; err != nil {
			tx.Rollback()
			c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
			return
		}
	}
	for _, cfg := range configRows {
		if !cfg.Enabled {
			continue
		}
		if err := tx.Exec(`
INSERT INTO machine_photo_tasks
  (serial_no, model_name, position_code, item_name, required, ocr_enabled, ocr_profile, status, sort_order, enabled, created_by)
VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', ?, 1, ?)
ON DUPLICATE KEY UPDATE
  model_name = VALUES(model_name),
  item_name = VALUES(item_name),
  required = VALUES(required),
  ocr_enabled = VALUES(ocr_enabled),
  ocr_profile = VALUES(ocr_profile),
  sort_order = VALUES(sort_order),
  enabled = 1,
  updated_at = CURRENT_TIMESTAMP`,
			serialNo,
			profile.Model,
			cfg.PositionCode,
			cfg.ItemName,
			cfg.Required,
			cfg.OCREnabled,
			cfg.OCRProfile,
			cfg.SortOrder,
			c.GetString("username"),
		).Error; err != nil {
			tx.Rollback()
			c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
			return
		}
	}
	if err := tx.Commit().Error; err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}
	h.respondTasks(c, serialNo)
}

func (h *PhotoHandler) MachinePhotoTasks(c *gin.Context) {
	h.respondTasks(c, strings.TrimSpace(c.Param("serialNo")))
}

func (h *PhotoHandler) UploadTaskPhoto(c *gin.Context) {
	taskID, err := strconv.ParseInt(c.Param("taskId"), 10, 64)
	if err != nil || taskID <= 0 {
		c.JSON(http.StatusBadRequest, gin.H{"error": "invalid task id"})
		return
	}
	var task machinePhotoTaskRow
	if err := h.db.Table("machine_photo_tasks").Where("id = ?", taskID).First(&task).Error; err != nil {
		c.JSON(http.StatusNotFound, gin.H{"error": "拍照任务不存在"})
		return
	}
	if !task.Enabled {
		c.JSON(http.StatusBadRequest, gin.H{"error": "拍照项已不在当前机型配置中，请刷新任务"})
		return
	}
	file, err := firstUploadedFile(c)
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}
	saved, err := h.saveUploadedTaskFile(c, task, file)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}
	nextStatus := "completed"
	if task.OCREnabled {
		nextStatus = "uploaded"
	}
	if err := h.db.Exec("DELETE FROM machine_photo_ocr_results WHERE task_id = ?", taskID).Error; err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}
	if err := h.db.Table("machine_component_bindings").
		Where("source_task_id = ?", taskID).
		Updates(map[string]interface{}{"active": false}).Error; err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}
	if err := h.db.Table("machine_photo_tasks").Where("id = ?", taskID).Updates(map[string]interface{}{"status": nextStatus}).Error; err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}
	c.JSON(http.StatusOK, gin.H{"success": true, "file": saved, "task_status": nextStatus})
}

func (h *PhotoHandler) DeleteTaskPhoto(c *gin.Context) {
	taskID, err := strconv.ParseInt(c.Param("taskId"), 10, 64)
	if err != nil || taskID <= 0 {
		c.JSON(http.StatusBadRequest, gin.H{"error": "invalid task id"})
		return
	}
	var task machinePhotoTaskRow
	if err := h.db.Table("machine_photo_tasks").Where("id = ?", taskID).First(&task).Error; err != nil {
		c.JSON(http.StatusNotFound, gin.H{"error": "拍照任务不存在"})
		return
	}
	if !task.Enabled {
		c.JSON(http.StatusBadRequest, gin.H{"error": "拍照项已不在当前机型配置中，请刷新任务"})
		return
	}
	var files []struct {
		FilePath  string `gorm:"column:file_path"`
		ThumbPath string `gorm:"column:thumb_path"`
	}
	if err := h.db.Table("machine_photo_files").
		Select("file_path, COALESCE(thumb_path, '') AS thumb_path").
		Where("task_id = ?", taskID).
		Find(&files).Error; err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	tx := h.db.Begin()
	if err := tx.Exec("DELETE FROM machine_photo_ocr_results WHERE task_id = ?", taskID).Error; err != nil {
		tx.Rollback()
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}
	if err := tx.Exec("DELETE FROM machine_photo_files WHERE task_id = ?", taskID).Error; err != nil {
		tx.Rollback()
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}
	if err := tx.Table("machine_photo_tasks").Where("id = ?", taskID).Updates(map[string]interface{}{
		"status":       "pending",
		"skip_reason":  nil,
		"submit_batch": nil,
	}).Error; err != nil {
		tx.Rollback()
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}
	if err := tx.Table("machine_component_bindings").
		Where("source_task_id = ?", taskID).
		Updates(map[string]interface{}{"active": false}).Error; err != nil {
		tx.Rollback()
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}
	if err := tx.Commit().Error; err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}
	seen := map[string]bool{}
	for _, file := range files {
		for _, path := range []string{file.FilePath, file.ThumbPath} {
			path = strings.TrimSpace(path)
			if path == "" || seen[path] {
				continue
			}
			seen[path] = true
			_ = removeLocalTaskFile(path)
		}
	}
	c.JSON(http.StatusOK, gin.H{"success": true, "status": "pending"})
}

func (h *PhotoHandler) RunTaskOCR(c *gin.Context) {
	taskID, err := strconv.ParseInt(c.Param("taskId"), 10, 64)
	if err != nil || taskID <= 0 {
		c.JSON(http.StatusBadRequest, gin.H{"error": "invalid task id"})
		return
	}
	var task machinePhotoTaskRow
	if err := h.db.Table("machine_photo_tasks").Where("id = ?", taskID).First(&task).Error; err != nil {
		c.JSON(http.StatusNotFound, gin.H{"error": "拍照任务不存在"})
		return
	}
	if !task.Enabled {
		c.JSON(http.StatusBadRequest, gin.H{"error": "拍照项已不在当前机型配置中，请刷新任务"})
		return
	}
	var file struct {
		ID       int64  `gorm:"column:id"`
		FilePath string `gorm:"column:file_path"`
	}
	if err := h.db.Table("machine_photo_files").Select("id, file_path").Where("task_id = ?", taskID).Order("id DESC").First(&file).Error; err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "请先上传照片"})
		return
	}
	rules, err := h.ocrRules(task.OCRProfile, task.PositionCode)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}
	if err := h.db.Table("machine_photo_tasks").Where("id = ?", taskID).Update("status", "ocr_processing").Error; err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}
	results, rawJSON, callErr := h.callOCRService(task, file.FilePath, rules)
	if callErr != nil {
		_ = h.writeEmptyOCRResults(taskID, file.ID, rules, "empty", callErr.Error())
		_ = h.db.Table("machine_photo_tasks").Where("id = ?", taskID).Update("status", "manual_review").Error
		c.JSON(http.StatusOK, gin.H{"success": false, "status": "manual_review", "error": callErr.Error()})
		return
	}
	status := h.persistOCRResults(taskID, file.ID, rules, results, rawJSON)
	if err := h.db.Table("machine_photo_tasks").Where("id = ?", taskID).Update("status", status).Error; err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}
	if err := h.syncComponentBindingFromTaskID(taskID); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}
	c.JSON(http.StatusOK, gin.H{"success": true, "status": status, "results": results})
}

func (h *PhotoHandler) DecodeTaskQR(c *gin.Context) {
	taskID, err := strconv.ParseInt(c.Param("taskId"), 10, 64)
	if err != nil || taskID <= 0 {
		c.JSON(http.StatusBadRequest, gin.H{"error": "invalid task id"})
		return
	}
	var file struct {
		FilePath string `gorm:"column:file_path"`
	}
	if err := h.db.Table("machine_photo_files").
		Select("file_path").
		Where("task_id = ?", taskID).
		Order("id DESC").
		First(&file).Error; err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "请先上传照片"})
		return
	}
	if h.qrServiceURL == "" {
		c.JSON(http.StatusOK, gin.H{"success": false, "value": "", "values": []string{}, "error": "QR服务未配置"})
		return
	}
	absolutePath, err := filepath.Abs(file.FilePath)
	if err != nil {
		c.JSON(http.StatusOK, gin.H{"success": false, "value": "", "values": []string{}, "error": err.Error()})
		return
	}
	payload, _ := json.Marshal(gin.H{"image_path": absolutePath})
	req, err := http.NewRequest(http.MethodPost, h.qrServiceURL, bytes.NewReader(payload))
	if err != nil {
		c.JSON(http.StatusOK, gin.H{"success": false, "value": "", "values": []string{}, "error": err.Error()})
		return
	}
	req.Header.Set("Content-Type", "application/json")
	if h.internalToken != "" {
		req.Header.Set("X-Internal-Token", h.internalToken)
	}
	client := &http.Client{Timeout: h.ocrTimeout}
	resp, err := client.Do(req)
	if err != nil {
		c.JSON(http.StatusOK, gin.H{"success": false, "value": "", "values": []string{}, "error": err.Error()})
		return
	}
	defer resp.Body.Close()
	responseBody, _ := io.ReadAll(resp.Body)
	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		c.JSON(http.StatusOK, gin.H{"success": false, "value": "", "values": []string{}, "error": string(responseBody)})
		return
	}
	var decoded struct {
		Success   bool     `json:"success"`
		Value     string   `json:"value"`
		Values    []string `json:"values"`
		Ambiguous bool     `json:"ambiguous"`
	}
	if err := json.Unmarshal(responseBody, &decoded); err != nil {
		c.JSON(http.StatusOK, gin.H{"success": false, "value": "", "values": []string{}, "error": err.Error()})
		return
	}
	c.JSON(http.StatusOK, decoded)
}

func (h *PhotoHandler) SaveTaskRecognition(c *gin.Context) {
	taskID, err := strconv.ParseInt(c.Param("taskId"), 10, 64)
	if err != nil || taskID <= 0 {
		c.JSON(http.StatusBadRequest, gin.H{"error": "invalid task id"})
		return
	}
	var req struct {
		Source    string `json:"source"`
		Value     string `json:"value"`
		FieldCode string `json:"field_code"`
		FieldName string `json:"field_name"`
	}
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "JSON body required"})
		return
	}
	source := strings.TrimSpace(req.Source)
	if source != "qr_static" {
		c.JSON(http.StatusBadRequest, gin.H{"error": "unsupported recognition source"})
		return
	}
	value := strings.TrimSpace(req.Value)
	if value == "" {
		c.JSON(http.StatusBadRequest, gin.H{"error": "识别结果不能为空"})
		return
	}
	if len([]rune(value)) > 100 {
		c.JSON(http.StatusBadRequest, gin.H{"error": "二维码标签编码不能超过100个字符"})
		return
	}
	var task machinePhotoTaskRow
	if err := h.db.Table("machine_photo_tasks").Where("id = ?", taskID).First(&task).Error; err != nil {
		c.JSON(http.StatusNotFound, gin.H{"error": "拍照任务不存在"})
		return
	}
	if !task.Enabled {
		c.JSON(http.StatusBadRequest, gin.H{"error": "拍照项已不在当前机型配置中，请刷新任务"})
		return
	}
	var fileID int64
	if err := h.db.Table("machine_photo_files").
		Select("id").
		Where("task_id = ?", taskID).
		Order("id DESC").
		Limit(1).
		Scan(&fileID).Error; err != nil || fileID <= 0 {
		c.JSON(http.StatusBadRequest, gin.H{"error": "请先上传照片"})
		return
	}
	fieldCode := strings.TrimSpace(req.FieldCode)
	if fieldCode == "" {
		fieldCode = "component_serial_no"
	}
	fieldName := strings.TrimSpace(req.FieldName)
	if fieldName == "" {
		fieldName = "标签编码"
	}
	raw, _ := json.Marshal(gin.H{"source": source})
	tx := h.db.Begin()
	if err := tx.Exec("DELETE FROM machine_photo_ocr_results WHERE task_id = ?", taskID).Error; err != nil {
		tx.Rollback()
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}
	if err := tx.Exec(`
INSERT INTO machine_photo_ocr_results
  (task_id, file_id, field_code, field_name, recognized_value, confidence, check_status, raw_result_json)
VALUES (?, ?, ?, ?, ?, 1, 'manual_review', ?)`,
		taskID, fileID, fieldCode, fieldName, value, string(raw)).Error; err != nil {
		tx.Rollback()
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}
	if err := tx.Table("machine_photo_tasks").Where("id = ?", taskID).Update("status", "manual_review").Error; err != nil {
		tx.Rollback()
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}
	if err := tx.Commit().Error; err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}
	c.JSON(http.StatusOK, gin.H{
		"success": true,
		"status":  "manual_review",
		"result": gin.H{
			"field_code":         fieldCode,
			"field_name":         fieldName,
			"recognized_value":   value,
			"confidence":         1,
			"check_status":       "manual_review",
			"recognition_source": source,
		},
	})
}

func (h *PhotoHandler) ConfirmTaskOCR(c *gin.Context) {
	taskID, err := strconv.ParseInt(c.Param("taskId"), 10, 64)
	if err != nil || taskID <= 0 {
		c.JSON(http.StatusBadRequest, gin.H{"error": "invalid task id"})
		return
	}
	var req struct {
		Fields []struct {
			FieldCode   string `json:"field_code"`
			FieldName   string `json:"field_name"`
			ManualValue string `json:"manual_value"`
			Passed      bool   `json:"passed"`
		} `json:"fields"`
		Status       string `json:"status"`
		RetakeReason string `json:"retake_reason"`
		SkipReason   string `json:"skip_reason"`
	}
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "JSON body required"})
		return
	}
	var task machinePhotoTaskRow
	if err := h.db.Table("machine_photo_tasks").Where("id = ?", taskID).First(&task).Error; err != nil {
		c.JSON(http.StatusNotFound, gin.H{"error": "拍照任务不存在"})
		return
	}
	if !task.Enabled {
		c.JSON(http.StatusBadRequest, gin.H{"error": "拍照项已不在当前机型配置中，请刷新任务"})
		return
	}
	nextStatus := normalizeTaskStatus(req.Status)
	if nextStatus == "" {
		nextStatus = "completed"
	}
	if nextStatus == "manual_passed" || nextStatus == "completed" {
		for _, field := range req.Fields {
			value := strings.TrimSpace(field.ManualValue)
			if !field.Passed || value == "" {
				continue
			}
			var duplicate struct {
				MachineNo    string `gorm:"column:machine_no"`
				PositionCode string `gorm:"column:position_code"`
			}
			err := h.db.Table("machine_component_bindings").
				Select("machine_no, position_code").
				Where("active = 1 AND component_serial_no = ? AND NOT (machine_no = ? AND position_code = ?)", value, task.SerialNo, task.PositionCode).
				Limit(1).
				Scan(&duplicate).Error
			if err != nil {
				c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
				return
			}
			if duplicate.MachineNo != "" {
				c.JSON(http.StatusConflict, gin.H{
					"error": fmt.Sprintf("标签编码已绑定到机台 %s 的位置 %s", duplicate.MachineNo, duplicate.PositionCode),
				})
				return
			}
		}
	}
	tx := h.db.Begin()
	var latestFileID int64
	if len(req.Fields) > 0 {
		_ = tx.Table("machine_photo_files").
			Select("id").
			Where("task_id = ?", taskID).
			Order("id DESC").
			Limit(1).
			Scan(&latestFileID).Error
	}
	for _, field := range req.Fields {
		fieldCode := strings.TrimSpace(field.FieldCode)
		if fieldCode == "" {
			continue
		}
		checkStatus := "manual_rejected"
		if field.Passed {
			checkStatus = "manual_passed"
		}
		manualValue := strings.TrimSpace(field.ManualValue)
		result := tx.Exec(`
UPDATE machine_photo_ocr_results
SET manual_value = ?, check_status = ?, reviewed_by = ?, reviewed_at = NOW(), updated_at = CURRENT_TIMESTAMP
WHERE task_id = ? AND field_code = ?`,
			manualValue, checkStatus, c.GetString("username"), taskID, fieldCode)
		if result.Error != nil {
			tx.Rollback()
			c.JSON(http.StatusInternalServerError, gin.H{"error": result.Error.Error()})
			return
		}
		if result.RowsAffected == 0 {
			fieldName := strings.TrimSpace(field.FieldName)
			if fieldName == "" {
				fieldName = "识别文本"
			}
			if err := tx.Exec(`
INSERT INTO machine_photo_ocr_results
  (task_id, file_id, field_code, field_name, recognized_value, manual_value, confidence, check_status, reviewed_by, reviewed_at, raw_result_json)
VALUES (?, ?, ?, ?, '', ?, 0, ?, ?, NOW(), ?)`,
				taskID, latestFileID, fieldCode, fieldName, manualValue, checkStatus, c.GetString("username"), "{}").Error; err != nil {
				tx.Rollback()
				c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
				return
			}
		}
	}
	updates := map[string]interface{}{"status": nextStatus}
	if strings.TrimSpace(req.SkipReason) != "" {
		updates["skip_reason"] = strings.TrimSpace(req.SkipReason)
	}
	if err := tx.Table("machine_photo_tasks").Where("id = ?", taskID).Updates(updates).Error; err != nil {
		tx.Rollback()
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}
	if err := tx.Commit().Error; err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}
	if err := h.syncComponentBindingFromTaskID(taskID); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}
	c.JSON(http.StatusOK, gin.H{"success": true, "status": nextStatus})
}

func (h *PhotoHandler) SubmitMachinePhotos(c *gin.Context) {
	serialNo := strings.TrimSpace(c.Param("serialNo"))
	tasks, err := h.loadMachinePhotoTasks(serialNo)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}
	if len(tasks) == 0 {
		c.JSON(http.StatusBadRequest, gin.H{"error": "请先生成拍照任务"})
		return
	}
	summary := buildMachinePhotoSummary(tasks)
	if intFromSummary(summary, "photo_done") == 0 {
		c.JSON(http.StatusBadRequest, gin.H{"error": "请至少先拍摄或上传一张照片"})
		return
	}
	submitBatch := fmt.Sprintf("PHOTO-%s-%d", safeName(serialNo), time.Now().Unix())
	summaryBytes, _ := json.Marshal(summary)
	modelName := tasks[0].ModelName
	if err := h.db.Exec(`
INSERT INTO machine_photo_submissions
  (serial_no, model_name, submit_batch, submitted_by, summary_json)
VALUES (?, ?, ?, ?, ?)`,
		serialNo, modelName, submitBatch, c.GetString("username"), string(summaryBytes)).Error; err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}
	_ = h.db.Table("machine_photo_tasks").Where("serial_no = ? AND enabled = 1", serialNo).Update("submit_batch", submitBatch).Error
	c.JSON(http.StatusOK, gin.H{"success": true, "submit_batch": submitBatch, "summary": summary})
}

func (h *PhotoHandler) DownloadTaskPhoto(c *gin.Context) {
	fileID, err := strconv.ParseInt(c.Param("fileId"), 10, 64)
	if err != nil || fileID <= 0 {
		c.JSON(http.StatusBadRequest, gin.H{"error": "invalid file id"})
		return
	}
	var file struct {
		FileName string `gorm:"column:file_name"`
		FilePath string `gorm:"column:file_path"`
	}
	if err := h.db.Table("machine_photo_files").Select("file_name, file_path").Where("id = ?", fileID).First(&file).Error; err != nil {
		c.JSON(http.StatusNotFound, gin.H{"error": "文件不存在"})
		return
	}
	c.FileAttachment(file.FilePath, file.FileName)
}

func (h *PhotoHandler) validateModelID(modelID int64) error {
	var count int64
	if err := h.db.Table("model_dictionary").Where("id = ?", modelID).Count(&count).Error; err != nil {
		return err
	}
	if count == 0 {
		return fmt.Errorf("机型不存在")
	}
	return nil
}

func (h *PhotoHandler) modelIDByName(modelName string) (int64, error) {
	var row struct {
		ID int64 `gorm:"column:id"`
	}
	name := strings.TrimSpace(modelName)
	if name == "" {
		return 0, fmt.Errorf("机型名称不能为空")
	}
	if err := h.db.Table("model_dictionary").
		Select("id").
		Where("TRIM(model_name) = ?", name).
		First(&row).Error; err != nil {
		return 0, fmt.Errorf("机型不存在: %s", name)
	}
	return row.ID, nil
}

func (h *PhotoHandler) replaceModelPhotoConfig(modelID int64, rows []modelPhotoConfigRow, actor string) error {
	if err := h.validateModelID(modelID); err != nil {
		return err
	}
	seen := map[string]bool{}
	for i := range rows {
		code := strings.ToUpper(strings.TrimSpace(rows[i].PositionCode))
		if code == "" {
			return fmt.Errorf("位置编码不能为空")
		}
		if seen[code] {
			return fmt.Errorf("同一机型不能重复配置位置编码: %s", code)
		}
		seen[code] = true
		if rows[i].OCREnabled && strings.TrimSpace(rows[i].OCRProfile) == "" {
			return fmt.Errorf("启用OCR时必须填写OCR方案: %s", code)
		}
		if err := h.validatePositionCode(code); err != nil {
			return err
		}
		rows[i].PositionCode = code
		rows[i].SortOrder = firstNonZero(rows[i].SortOrder, i+1)
	}
	tx := h.db.Begin()
	if err := tx.Exec("DELETE FROM model_photo_config WHERE model_id = ?", modelID).Error; err != nil {
		tx.Rollback()
		return err
	}
	for _, row := range rows {
		if err := tx.Exec(`
INSERT INTO model_photo_config
  (model_id, position_code, required, ocr_enabled, ocr_profile, sort_order, enabled, remark, updated_by)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)`,
			modelID,
			row.PositionCode,
			row.Required,
			row.OCREnabled,
			strings.TrimSpace(row.OCRProfile),
			row.SortOrder,
			row.Enabled,
			strings.TrimSpace(row.Remark),
			actor,
		).Error; err != nil {
			tx.Rollback()
			return err
		}
	}
	activeCodes := make([]string, 0, len(rows))
	for _, row := range rows {
		if !row.Enabled {
			continue
		}
		activeCodes = append(activeCodes, row.PositionCode)
		if err := tx.Exec(`
UPDATE machine_photo_tasks t
JOIN photo_item_library pil ON pil.position_code = t.position_code
SET
  t.item_name = pil.item_name,
  t.required = ?,
  t.ocr_enabled = ?,
  t.ocr_profile = ?,
  t.sort_order = ?,
  t.enabled = 1,
  t.updated_at = CURRENT_TIMESTAMP
WHERE TRIM(t.model_name) = (SELECT TRIM(model_name) FROM model_dictionary WHERE id = ?)
  AND t.position_code = ?`,
			row.Required,
			row.OCREnabled,
			strings.TrimSpace(row.OCRProfile),
			row.SortOrder,
			modelID,
			row.PositionCode,
		).Error; err != nil {
			tx.Rollback()
			return err
		}
	}
	if len(activeCodes) > 0 {
		if err := tx.Exec(`
UPDATE machine_photo_tasks
SET enabled = 0, updated_at = CURRENT_TIMESTAMP
WHERE TRIM(model_name) = (SELECT TRIM(model_name) FROM model_dictionary WHERE id = ?)
  AND position_code NOT IN ?`, modelID, activeCodes).Error; err != nil {
			tx.Rollback()
			return err
		}
		if err := tx.Exec(`
UPDATE machine_component_bindings
SET active = 0, updated_at = CURRENT_TIMESTAMP
WHERE TRIM(model_name) = (SELECT TRIM(model_name) FROM model_dictionary WHERE id = ?)
  AND position_code NOT IN ?`, modelID, activeCodes).Error; err != nil {
			tx.Rollback()
			return err
		}
	} else {
		if err := tx.Exec(`
UPDATE machine_photo_tasks
SET enabled = 0, updated_at = CURRENT_TIMESTAMP
WHERE TRIM(model_name) = (SELECT TRIM(model_name) FROM model_dictionary WHERE id = ?)`, modelID).Error; err != nil {
			tx.Rollback()
			return err
		}
		if err := tx.Exec(`
UPDATE machine_component_bindings
SET active = 0, updated_at = CURRENT_TIMESTAMP
WHERE TRIM(model_name) = (SELECT TRIM(model_name) FROM model_dictionary WHERE id = ?)`, modelID).Error; err != nil {
			tx.Rollback()
			return err
		}
	}
	return tx.Commit().Error
}

func (h *PhotoHandler) validatePositionCode(code string) error {
	var count int64
	if err := h.db.Table("photo_item_library").Where("position_code = ?", code).Count(&count).Error; err != nil {
		return err
	}
	if count == 0 {
		return fmt.Errorf("位置编码不存在: %s", code)
	}
	return nil
}

func (h *PhotoHandler) readPhotoImportPayload(c *gin.Context) (photoImportPayload, error) {
	if strings.Contains(strings.ToLower(c.GetHeader("Content-Type")), "multipart/form-data") {
		file, err := c.FormFile("file")
		if err != nil {
			return photoImportPayload{}, fmt.Errorf("请上传Excel文件")
		}
		return parsePhotoImportExcel(file)
	}
	var req photoImportPayload
	if err := c.ShouldBindJSON(&req); err != nil {
		return req, fmt.Errorf("JSON导入数据格式不正确")
	}
	return req, nil
}

const (
	photoItemsSheetName  = "拍照项目库"
	modelConfigSheetName = "机型拍照配置"
	ocrRulesSheetName    = "OCR字段规则"
)

func parsePhotoImportExcel(file *multipart.FileHeader) (photoImportPayload, error) {
	src, err := file.Open()
	if err != nil {
		return photoImportPayload{}, err
	}
	defer src.Close()
	workbook, err := excelize.OpenReader(src)
	if err != nil {
		return photoImportPayload{}, fmt.Errorf("Excel文件读取失败: %w", err)
	}
	defer workbook.Close()

	var payload photoImportPayload
	if payload.PhotoItems, err = parsePhotoItemsSheet(workbook); err != nil {
		return payload, err
	}
	if payload.ModelConfig, err = parseModelConfigSheet(workbook); err != nil {
		return payload, err
	}
	if payload.OCRRules, err = parseOCRRulesSheet(workbook); err != nil {
		return payload, err
	}
	if len(payload.PhotoItems) == 0 && len(payload.ModelConfig) == 0 && len(payload.OCRRules) == 0 {
		return payload, fmt.Errorf("Excel导入文件没有可导入数据")
	}
	return payload, nil
}

func parsePhotoItemsSheet(workbook *excelize.File) ([]photoItemRow, error) {
	rows, ok, err := importSheetRows(workbook, photoItemsSheetName)
	if err != nil || !ok || len(rows) <= 1 {
		return nil, err
	}
	headers := importHeaders(rows[0])
	if err := requireImportHeaders(photoItemsSheetName, headers, "position_code", "item_name"); err != nil {
		return nil, err
	}
	items := make([]photoItemRow, 0, len(rows)-1)
	for idx, row := range rows[1:] {
		if importRowEmpty(row) {
			continue
		}
		sortOrder, err := parseImportInt(importCell(row, headers, "sort_order"), len(items)+1)
		if err != nil {
			return nil, fmt.Errorf("%s第%d行排序不是数字", photoItemsSheetName, idx+2)
		}
		required, err := parseImportBool(importCell(row, headers, "default_required"), true)
		if err != nil {
			return nil, fmt.Errorf("%s第%d行默认必拍字段不合法", photoItemsSheetName, idx+2)
		}
		ocrEnabled, err := parseImportBool(importCell(row, headers, "default_ocr_enabled"), false)
		if err != nil {
			return nil, fmt.Errorf("%s第%d行默认OCR字段不合法", photoItemsSheetName, idx+2)
		}
		enabled, err := parseImportBool(importCell(row, headers, "enabled"), true)
		if err != nil {
			return nil, fmt.Errorf("%s第%d行启用字段不合法", photoItemsSheetName, idx+2)
		}
		items = append(items, photoItemRow{
			PositionCode:        strings.ToUpper(strings.TrimSpace(importCell(row, headers, "position_code"))),
			ItemName:            strings.TrimSpace(importCell(row, headers, "item_name")),
			ItemCategory:        strings.TrimSpace(importCell(row, headers, "item_category")),
			ShootingRequirement: strings.TrimSpace(importCell(row, headers, "shooting_requirement")),
			DefaultRequired:     required,
			DefaultOCREnabled:   ocrEnabled,
			DefaultOCRProfile:   strings.TrimSpace(importCell(row, headers, "default_ocr_profile")),
			SortOrder:           sortOrder,
			Enabled:             enabled,
		})
	}
	return items, nil
}

func parseModelConfigSheet(workbook *excelize.File) ([]modelPhotoConfigRow, error) {
	rows, ok, err := importSheetRows(workbook, modelConfigSheetName)
	if err != nil || !ok || len(rows) <= 1 {
		return nil, err
	}
	headers := importHeaders(rows[0])
	if err := requireImportHeaders(modelConfigSheetName, headers, "position_code"); err != nil {
		return nil, err
	}
	configs := make([]modelPhotoConfigRow, 0, len(rows)-1)
	for idx, row := range rows[1:] {
		if importRowEmpty(row) {
			continue
		}
		modelID, err := parseImportInt(importCell(row, headers, "model_id"), 0)
		if err != nil {
			return nil, fmt.Errorf("%s第%d行model_id不是数字", modelConfigSheetName, idx+2)
		}
		sortOrder, err := parseImportInt(importCell(row, headers, "sort_order"), len(configs)+1)
		if err != nil {
			return nil, fmt.Errorf("%s第%d行排序不是数字", modelConfigSheetName, idx+2)
		}
		required, err := parseImportBool(importCell(row, headers, "required"), true)
		if err != nil {
			return nil, fmt.Errorf("%s第%d行必拍字段不合法", modelConfigSheetName, idx+2)
		}
		ocrEnabled, err := parseImportBool(importCell(row, headers, "ocr_enabled"), false)
		if err != nil {
			return nil, fmt.Errorf("%s第%d行OCR字段不合法", modelConfigSheetName, idx+2)
		}
		enabled, err := parseImportBool(importCell(row, headers, "enabled"), true)
		if err != nil {
			return nil, fmt.Errorf("%s第%d行启用字段不合法", modelConfigSheetName, idx+2)
		}
		configs = append(configs, modelPhotoConfigRow{
			ModelID:      int64(modelID),
			ModelName:    strings.TrimSpace(importCell(row, headers, "model_name")),
			PositionCode: strings.ToUpper(strings.TrimSpace(importCell(row, headers, "position_code"))),
			Required:     required,
			OCREnabled:   ocrEnabled,
			OCRProfile:   strings.TrimSpace(importCell(row, headers, "ocr_profile")),
			SortOrder:    sortOrder,
			Enabled:      enabled,
			Remark:       strings.TrimSpace(importCell(row, headers, "remark")),
		})
	}
	return configs, nil
}

func parseOCRRulesSheet(workbook *excelize.File) ([]ocrFieldRuleRow, error) {
	rows, ok, err := importSheetRows(workbook, ocrRulesSheetName)
	if err != nil || !ok || len(rows) <= 1 {
		return nil, err
	}
	headers := importHeaders(rows[0])
	if err := requireImportHeaders(ocrRulesSheetName, headers, "ocr_profile", "position_code", "field_code", "field_name"); err != nil {
		return nil, err
	}
	rules := make([]ocrFieldRuleRow, 0, len(rows)-1)
	for idx, row := range rows[1:] {
		if importRowEmpty(row) {
			continue
		}
		required, err := parseImportBool(importCell(row, headers, "required"), true)
		if err != nil {
			return nil, fmt.Errorf("%s第%d行必填字段不合法", ocrRulesSheetName, idx+2)
		}
		threshold, err := parseImportFloat(importCell(row, headers, "confidence_threshold"), 0.8)
		if err != nil {
			return nil, fmt.Errorf("%s第%d行置信度不是数字", ocrRulesSheetName, idx+2)
		}
		enabled, err := parseImportBool(importCell(row, headers, "enabled"), true)
		if err != nil {
			return nil, fmt.Errorf("%s第%d行启用字段不合法", ocrRulesSheetName, idx+2)
		}
		rules = append(rules, ocrFieldRuleRow{
			OCRProfile:          strings.TrimSpace(importCell(row, headers, "ocr_profile")),
			PositionCode:        strings.ToUpper(strings.TrimSpace(importCell(row, headers, "position_code"))),
			FieldCode:           strings.TrimSpace(importCell(row, headers, "field_code")),
			FieldName:           strings.TrimSpace(importCell(row, headers, "field_name")),
			Required:            required,
			Pattern:             strings.TrimSpace(importCell(row, headers, "pattern")),
			ConfidenceThreshold: threshold,
			CompareTarget:       strings.TrimSpace(importCell(row, headers, "compare_target")),
			Enabled:             enabled,
		})
	}
	return rules, nil
}

func importSheetRows(workbook *excelize.File, sheetName string) ([][]string, bool, error) {
	for _, name := range workbook.GetSheetList() {
		if strings.EqualFold(strings.TrimSpace(name), sheetName) {
			rows, err := workbook.GetRows(name)
			return rows, true, err
		}
	}
	return nil, false, nil
}

func importHeaders(row []string) map[string]int {
	headers := map[string]int{}
	for idx, value := range row {
		key := normalizeImportHeader(value)
		if key != "" {
			headers[key] = idx
		}
	}
	return headers
}

func normalizeImportHeader(value string) string {
	key := strings.ToLower(strings.TrimSpace(value))
	key = strings.NewReplacer(" ", "", "　", "", "_", "", "-", "", "/", "", "（", "", "）", "", "(", "", ")", "").Replace(key)
	switch key {
	case "positioncode", "位置编码":
		return "position_code"
	case "itemname", "项目名称", "拍照项目", "拍照项目名称":
		return "item_name"
	case "itemcategory", "大类", "项目大类":
		return "item_category"
	case "shootingrequirement", "拍摄要求", "拍照要求":
		return "shooting_requirement"
	case "defaultrequired", "默认必拍":
		return "default_required"
	case "defaultocrenabled", "默认ocr":
		return "default_ocr_enabled"
	case "defaultocrprofile", "默认ocr方案":
		return "default_ocr_profile"
	case "modelid":
		return "model_id"
	case "modelname", "机型", "机型名称":
		return "model_name"
	case "required", "必拍", "必填":
		return "required"
	case "ocrenabled", "ocr", "启用ocr":
		return "ocr_enabled"
	case "ocrprofile", "ocr方案":
		return "ocr_profile"
	case "fieldcode", "字段编码":
		return "field_code"
	case "fieldname", "字段名称":
		return "field_name"
	case "pattern", "格式正则", "校验正则":
		return "pattern"
	case "confidencethreshold", "置信度", "置信度阈值":
		return "confidence_threshold"
	case "comparetarget", "比对目标", "比对字段":
		return "compare_target"
	case "sortorder", "排序":
		return "sort_order"
	case "enabled", "启用", "是否启用":
		return "enabled"
	case "remark", "备注":
		return "remark"
	default:
		return key
	}
}

func requireImportHeaders(sheetName string, headers map[string]int, keys ...string) error {
	for _, key := range keys {
		if _, ok := headers[key]; !ok {
			return fmt.Errorf("%s缺少必填列: %s", sheetName, key)
		}
	}
	return nil
}

func importCell(row []string, headers map[string]int, key string) string {
	idx, ok := headers[key]
	if !ok || idx >= len(row) {
		return ""
	}
	return strings.TrimSpace(row[idx])
}

func importRowEmpty(row []string) bool {
	for _, value := range row {
		if strings.TrimSpace(value) != "" {
			return false
		}
	}
	return true
}

func parseImportBool(value string, defaultValue bool) (bool, error) {
	raw := strings.TrimSpace(value)
	if raw == "" {
		return defaultValue, nil
	}
	key := strings.ToLower(raw)
	switch key {
	case "1", "true", "yes", "y", "是", "启用", "开", "必拍", "必填", "有", "√":
		return true, nil
	case "0", "false", "no", "n", "否", "禁用", "关", "非必拍", "非必填", "无", "×", "x":
		return false, nil
	default:
		return false, fmt.Errorf("invalid bool value: %s", raw)
	}
}

func parseImportInt(value string, defaultValue int) (int, error) {
	raw := strings.TrimSpace(value)
	if raw == "" {
		return defaultValue, nil
	}
	parsed, err := strconv.ParseFloat(raw, 64)
	if err != nil {
		return 0, err
	}
	return int(parsed), nil
}

func parseImportFloat(value string, defaultValue float64) (float64, error) {
	raw := strings.TrimSpace(value)
	if raw == "" {
		return defaultValue, nil
	}
	return strconv.ParseFloat(raw, 64)
}

func buildPhotoImportTemplate() (*excelize.File, error) {
	file := excelize.NewFile()
	if err := file.SetSheetName("Sheet1", photoItemsSheetName); err != nil {
		return nil, err
	}
	if err := writeImportSheet(file, photoItemsSheetName,
		[]string{"位置编码", "项目名称", "大类", "拍摄要求", "默认必拍", "默认OCR", "默认OCR方案", "排序", "启用"},
		[][]interface{}{
			{"SN-PLC", "PLC编号", "电控", "拍清编号标签，避免反光", "是", "是", "编号标签OCR", 10, "是"},
			{"SN-CPU", "CPU板编号", "电控", "拍清整块板卡与编号标签", "是", "是", "编号标签OCR", 20, "是"},
		}); err != nil {
		return nil, err
	}
	if _, err := file.NewSheet(modelConfigSheetName); err != nil {
		return nil, err
	}
	if err := writeImportSheet(file, modelConfigSheetName,
		[]string{"机型", "位置编码", "必拍", "OCR", "OCR方案", "排序", "启用", "备注"},
		[][]interface{}{
			{"FR-400AUTO", "SN-PLC", "是", "是", "编号标签OCR", 10, "是", ""},
			{"FR-400AUTO", "SN-CPU", "是", "是", "编号标签OCR", 20, "是", ""},
		}); err != nil {
		return nil, err
	}
	if _, err := file.NewSheet(ocrRulesSheetName); err != nil {
		return nil, err
	}
	if err := writeImportSheet(file, ocrRulesSheetName,
		[]string{"OCR方案", "位置编码", "字段编码", "字段名称", "必填", "格式正则", "置信度", "比对目标", "启用"},
		[][]interface{}{
			{"编号标签OCR", "SN-PLC", "plc_no", "PLC编号", "是", "", 0.8, "", "是"},
			{"编号标签OCR", "SN-CPU", "cpu_board_no", "CPU板编号", "是", "", 0.8, "", "是"},
		}); err != nil {
		return nil, err
	}
	index, err := file.GetSheetIndex(photoItemsSheetName)
	if err == nil {
		file.SetActiveSheet(index)
	}
	return file, nil
}

func writeImportSheet(file *excelize.File, sheet string, headers []string, rows [][]interface{}) error {
	headerStyle, _ := file.NewStyle(&excelize.Style{
		Font: &excelize.Font{Bold: true, Color: "FFFFFF"},
		Fill: excelize.Fill{Type: "pattern", Color: []string{"4472C4"}, Pattern: 1},
	})
	for idx, header := range headers {
		cell, _ := excelize.CoordinatesToCellName(idx+1, 1)
		if err := file.SetCellValue(sheet, cell, header); err != nil {
			return err
		}
		_ = file.SetCellStyle(sheet, cell, cell, headerStyle)
	}
	for rowIdx, row := range rows {
		for colIdx, value := range row {
			cell, _ := excelize.CoordinatesToCellName(colIdx+1, rowIdx+2)
			if err := file.SetCellValue(sheet, cell, value); err != nil {
				return err
			}
		}
	}
	for idx := range headers {
		col, _ := excelize.ColumnNumberToName(idx + 1)
		_ = file.SetColWidth(sheet, col, col, 16)
	}
	return nil
}

func (h *PhotoHandler) saveOCRRules(rows []ocrFieldRuleRow) error {
	tx := h.db.Begin()
	for _, row := range rows {
		profile := strings.TrimSpace(row.OCRProfile)
		code := strings.ToUpper(strings.TrimSpace(row.PositionCode))
		fieldCode := strings.TrimSpace(row.FieldCode)
		fieldName := strings.TrimSpace(row.FieldName)
		if profile == "" || code == "" || fieldCode == "" || fieldName == "" {
			tx.Rollback()
			return fmt.Errorf("OCR方案、位置编码、字段编码、字段名称不能为空")
		}
		if err := h.validatePositionCode(code); err != nil {
			tx.Rollback()
			return err
		}
		threshold := row.ConfidenceThreshold
		if threshold <= 0 {
			threshold = 0.8
		}
		if err := tx.Exec(`
INSERT INTO ocr_field_rules
  (ocr_profile, position_code, field_code, field_name, required, pattern, confidence_threshold, compare_target, enabled)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
ON DUPLICATE KEY UPDATE
  field_name = VALUES(field_name),
  required = VALUES(required),
  pattern = VALUES(pattern),
  confidence_threshold = VALUES(confidence_threshold),
  compare_target = VALUES(compare_target),
  enabled = VALUES(enabled),
  updated_at = CURRENT_TIMESTAMP`,
			profile, code, fieldCode, fieldName, row.Required, strings.TrimSpace(row.Pattern), threshold, strings.TrimSpace(row.CompareTarget), row.Enabled).Error; err != nil {
			tx.Rollback()
			return err
		}
	}
	return tx.Commit().Error
}

func (h *PhotoHandler) modelPhotoConfigByName(modelName string) ([]modelPhotoConfigRow, error) {
	var rows []modelPhotoConfigRow
	err := h.db.Raw(`
SELECT
  mpc.id,
  mpc.model_id,
  md.model_name,
  mpc.position_code,
  pil.item_name,
  COALESCE(pil.item_category, '') AS item_category,
  COALESCE(pil.shooting_requirement, '') AS shooting_requirement,
  mpc.required,
  mpc.ocr_enabled,
  COALESCE(mpc.ocr_profile, '') AS ocr_profile,
  mpc.sort_order,
  mpc.enabled,
  COALESCE(mpc.remark, '') AS remark
FROM model_dictionary md
JOIN model_photo_config mpc ON mpc.model_id = md.id
JOIN photo_item_library pil ON pil.position_code = mpc.position_code
WHERE TRIM(md.model_name) = ?
  AND md.enabled = 1
  AND mpc.enabled = 1
  AND pil.enabled = 1
ORDER BY mpc.sort_order ASC, mpc.position_code ASC`, strings.TrimSpace(modelName)).Scan(&rows).Error
	return rows, err
}

func (h *PhotoHandler) loadMachineProfile(c *gin.Context, serialNo string) (machineProfileRow, bool) {
	var row machineProfileRow
	if serialNo == "" {
		c.JSON(http.StatusBadRequest, gin.H{"error": "流水号不能为空"})
		return row, false
	}
	err := h.db.Raw(`
SELECT
  COALESCE(`+"`批次号`"+`, '') AS batch_no,
  COALESCE(`+"`机型`"+`, '') AS model,
  COALESCE(`+"`流水号`"+`, '') AS serial_no,
  COALESCE(`+"`状态`"+`, '') AS status,
  COALESCE(`+"`Location_Code`"+`, '') AS slot_code
FROM finished_goods_data
WHERE TRIM(`+"`流水号`"+`) = ?
LIMIT 1`, serialNo).Scan(&row).Error
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return row, false
	}
	if strings.TrimSpace(row.SerialNo) == "" {
		c.JSON(http.StatusNotFound, gin.H{"error": "未找到该机台流水号"})
		return row, false
	}
	if strings.TrimSpace(row.Model) == "" {
		c.JSON(http.StatusBadRequest, gin.H{"error": "该机台未维护机型"})
		return row, false
	}
	return row, true
}

func (h *PhotoHandler) respondTasks(c *gin.Context, serialNo string) {
	rows, err := h.loadMachinePhotoTasks(serialNo)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}
	c.JSON(http.StatusOK, gin.H{
		"data":    rows,
		"summary": buildMachinePhotoSummary(rows),
	})
}

func (h *PhotoHandler) loadMachinePhotoTasks(serialNo string) ([]machinePhotoTaskRow, error) {
	var rows []machinePhotoTaskRow
	if err := h.db.Raw(`
SELECT
  t.id,
  t.serial_no,
  t.model_name,
  t.position_code,
  t.item_name,
  t.required,
  t.ocr_enabled,
  COALESCE(t.ocr_profile, '') AS ocr_profile,
  t.status,
  t.sort_order,
  t.enabled,
  f.id AS file_id,
  COALESCE(f.file_name, '') AS file_name,
  COALESCE(DATE_FORMAT(f.uploaded_at, '%Y-%m-%d %H:%i:%s'), '') AS uploaded_at,
  COALESCE(SUM(CASE WHEN r.check_status IN ('low_confidence','empty','pattern_failed','manual_rejected') THEN 1 ELSE 0 END), 0) AS ocr_issues
FROM machine_photo_tasks t
LEFT JOIN machine_photo_files f ON f.id = (
  SELECT mf.id FROM machine_photo_files mf WHERE mf.task_id = t.id ORDER BY mf.id DESC LIMIT 1
)
LEFT JOIN machine_photo_ocr_results r ON r.task_id = t.id
	WHERE t.serial_no = ?
	  AND t.enabled = 1
	GROUP BY t.id, f.id
	ORDER BY t.sort_order ASC, t.position_code ASC`, serialNo).Scan(&rows).Error; err != nil {
		return nil, err
	}
	if err := h.attachOCRResults(rows); err != nil {
		return nil, err
	}
	return rows, nil
}

func buildMachinePhotoSummary(rows []machinePhotoTaskRow) gin.H {
	requiredTotal := 0
	requiredDone := 0
	requiredPhotoDone := 0
	photoDone := 0
	ocrTotal := 0
	ocrConfirmed := 0
	ocrPending := 0
	retakeRequired := 0
	for _, row := range rows {
		hasPhoto := taskHasPhoto(row)
		confirmed := taskHasConfirmedOCR(row)
		if hasPhoto {
			photoDone++
		}
		if row.Required {
			requiredTotal++
			if taskStatusSubmittable(row.Status) {
				requiredDone++
			}
			if hasPhoto {
				requiredPhotoDone++
			}
		}
		if row.OCREnabled {
			ocrTotal++
			if confirmed {
				ocrConfirmed++
			} else if hasPhoto || strings.TrimSpace(row.Status) != "pending" {
				ocrPending++
			}
		}
		if row.Status == "retake_required" {
			retakeRequired++
		}
	}
	return gin.H{
		"total":               len(rows),
		"required_total":      requiredTotal,
		"required_done":       requiredDone,
		"required_photo_done": requiredPhotoDone,
		"photo_done":          photoDone,
		"ocr_total":           ocrTotal,
		"ocr_confirmed":       ocrConfirmed,
		"ocr_pending":         ocrPending,
		"missing_required":    maxInt(requiredTotal-requiredPhotoDone, 0),
		"retake_required":     retakeRequired,
		"can_submit":          len(rows) > 0 && photoDone > 0,
	}
}

func (h *PhotoHandler) attachOCRResults(tasks []machinePhotoTaskRow) error {
	if len(tasks) == 0 {
		return nil
	}
	taskIDs := make([]int64, 0, len(tasks))
	for _, task := range tasks {
		taskIDs = append(taskIDs, task.ID)
	}
	var results []ocrResultRow
	if err := h.db.Raw(`
SELECT
  id,
  task_id,
  field_code,
  field_name,
  COALESCE(recognized_value, '') AS recognized_value,
  COALESCE(manual_value, '') AS manual_value,
  COALESCE(NULLIF(manual_value, ''), COALESCE(recognized_value, '')) AS display_value,
  COALESCE(confidence, 0) AS confidence,
  check_status,
  COALESCE(JSON_UNQUOTE(JSON_EXTRACT(raw_result_json, '$.source')), 'ocr') AS recognition_source
FROM machine_photo_ocr_results
WHERE task_id IN ?
ORDER BY id ASC`, taskIDs).Scan(&results).Error; err != nil {
		return err
	}
	byTask := map[int64][]ocrResultRow{}
	for _, result := range results {
		byTask[result.TaskID] = append(byTask[result.TaskID], result)
	}
	for i := range tasks {
		tasks[i].OCRResults = byTask[tasks[i].ID]
		if len(tasks[i].OCRResults) == 0 && tasks[i].OCREnabled && (tasks[i].FileName != "" || tasks[i].Status != "pending") {
			fieldName := strings.TrimSpace(tasks[i].ItemName)
			if fieldName == "" {
				fieldName = "识别文本"
			}
			tasks[i].OCRResults = []ocrResultRow{{
				TaskID:      tasks[i].ID,
				FieldCode:   "recognized_text",
				FieldName:   fieldName,
				CheckStatus: "manual_review",
			}}
		}
	}
	return nil
}

func firstUploadedFile(c *gin.Context) (*multipart.FileHeader, error) {
	form, err := c.MultipartForm()
	if err != nil {
		file, singleErr := c.FormFile("file")
		if singleErr == nil {
			return file, nil
		}
		return nil, fmt.Errorf("请选择照片文件")
	}
	for _, key := range []string{"file", "files"} {
		files := form.File[key]
		if len(files) > 0 {
			return files[0], nil
		}
	}
	return nil, fmt.Errorf("请选择照片文件")
}

func (h *PhotoHandler) saveUploadedTaskFile(c *gin.Context, task machinePhotoTaskRow, file *multipart.FileHeader) (gin.H, error) {
	ext := strings.ToLower(filepath.Ext(file.Filename))
	if ext == "" {
		ext = ".jpg"
	}
	fileName := fmt.Sprintf("%s_%s_%d%s", safeName(task.SerialNo), safeName(task.PositionCode), time.Now().UnixNano(), ext)
	dir := filepath.Join("data", "machine_photo_tasks", safeName(task.SerialNo), safeName(task.PositionCode))
	if err := os.MkdirAll(dir, 0755); err != nil {
		return nil, err
	}
	path := filepath.Join(dir, fileName)
	if err := c.SaveUploadedFile(file, path); err != nil {
		return nil, err
	}
	mimeType := file.Header.Get("Content-Type")
	if err := h.db.Exec(`
INSERT INTO machine_photo_files
  (task_id, serial_no, position_code, file_name, file_path, thumb_path, mime_type, file_size, uploaded_by)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)`,
		task.ID,
		task.SerialNo,
		task.PositionCode,
		fileName,
		path,
		path,
		mimeType,
		file.Size,
		c.GetString("username"),
	).Error; err != nil {
		return nil, err
	}
	var fileID int64
	if err := h.db.Table("machine_photo_files").
		Select("id").
		Where("task_id = ? AND file_name = ?", task.ID, fileName).
		Order("id DESC").
		Limit(1).
		Scan(&fileID).Error; err != nil {
		return nil, err
	}
	return gin.H{"id": fileID, "file_name": fileName, "file_size": file.Size}, nil
}

func (h *PhotoHandler) ocrRules(profile string, positionCode string) ([]ocrFieldRuleRow, error) {
	var rows []ocrFieldRuleRow
	err := h.db.Table("ocr_field_rules").
		Where("ocr_profile = ? AND position_code = ? AND enabled = 1", strings.TrimSpace(profile), strings.TrimSpace(positionCode)).
		Order("field_code ASC").
		Find(&rows).Error
	return rows, err
}

type ocrServiceField struct {
	FieldCode       string  `json:"field_code"`
	FieldName       string  `json:"field_name"`
	RecognizedValue string  `json:"recognized_value"`
	Value           string  `json:"value"`
	Confidence      float64 `json:"confidence"`
}

func (h *PhotoHandler) callOCRService(task machinePhotoTaskRow, filePath string, rules []ocrFieldRuleRow) ([]ocrServiceField, string, error) {
	if !h.ocrEnabled || h.ocrServiceURL == "" {
		return nil, "{}", fmt.Errorf("OCR服务未启用")
	}
	payload := gin.H{
		"image_path":    filePath,
		"ocr_profile":   task.OCRProfile,
		"position_code": task.PositionCode,
		"fields":        rules,
	}
	body, _ := json.Marshal(payload)
	client := &http.Client{Timeout: h.ocrTimeout}
	resp, err := client.Post(h.ocrServiceURL, "application/json", bytes.NewReader(body))
	if err != nil {
		return nil, "{}", err
	}
	defer resp.Body.Close()
	respBody, _ := io.ReadAll(resp.Body)
	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		return nil, string(respBody), fmt.Errorf("OCR服务返回异常: %s", resp.Status)
	}
	var parsed struct {
		Fields  []ocrServiceField `json:"fields"`
		Results []ocrServiceField `json:"results"`
		RawText string            `json:"raw_text"`
		Text    string            `json:"text"`
		Value   string            `json:"value"`
	}
	if err := json.Unmarshal(respBody, &parsed); err != nil {
		return nil, string(respBody), err
	}
	fields := parsed.Fields
	if len(fields) == 0 {
		fields = parsed.Results
	}
	if len(fields) == 0 {
		textValue := strings.TrimSpace(parsed.RawText)
		if textValue == "" {
			textValue = strings.TrimSpace(parsed.Text)
		}
		if textValue == "" {
			textValue = strings.TrimSpace(parsed.Value)
		}
		if textValue != "" {
			fields = []ocrServiceField{{
				FieldCode:       "recognized_text",
				FieldName:       "识别文本",
				RecognizedValue: textValue,
			}}
		}
	}
	return fields, string(respBody), nil
}

func (h *PhotoHandler) persistOCRResults(taskID int64, fileID int64, rules []ocrFieldRuleRow, results []ocrServiceField, rawJSON string) string {
	_ = h.db.Exec("DELETE FROM machine_photo_ocr_results WHERE task_id = ?", taskID).Error
	resultByCode := map[string]ocrServiceField{}
	for _, result := range results {
		code := strings.TrimSpace(result.FieldCode)
		if code != "" {
			resultByCode[code] = result
		}
	}
	if len(rules) == 0 {
		if len(results) == 0 {
			results = []ocrServiceField{{
				FieldCode:       "recognized_text",
				FieldName:       "识别文本",
				RecognizedValue: "",
			}}
		}
		for i, result := range results {
			fieldCode := strings.TrimSpace(result.FieldCode)
			if fieldCode == "" {
				fieldCode = "recognized_text"
				if i > 0 {
					fieldCode = fmt.Sprintf("recognized_text_%d", i+1)
				}
			}
			fieldName := strings.TrimSpace(result.FieldName)
			if fieldName == "" {
				fieldName = "识别文本"
			}
			value := recognizedOCRValue(result)
			_ = h.db.Exec(`
INSERT INTO machine_photo_ocr_results
  (task_id, file_id, field_code, field_name, recognized_value, confidence, check_status, raw_result_json)
VALUES (?, ?, ?, ?, ?, ?, 'manual_review', ?)`,
				taskID, fileID, fieldCode, fieldName, value, result.Confidence, rawJSON).Error
		}
		return "manual_review"
	}
	hasIssue := false
	for _, rule := range rules {
		result := resultByCode[rule.FieldCode]
		value := recognizedOCRValue(result)
		status := "passed"
		if value == "" && rule.Required {
			status = "empty"
		} else if result.Confidence > 0 && result.Confidence < rule.ConfidenceThreshold {
			status = "low_confidence"
		} else if strings.TrimSpace(rule.Pattern) != "" {
			if matched, err := regexp.MatchString(rule.Pattern, value); err == nil && !matched {
				status = "pattern_failed"
			}
		}
		if status != "passed" {
			hasIssue = true
		}
		_ = h.db.Exec(`
INSERT INTO machine_photo_ocr_results
  (task_id, file_id, field_code, field_name, recognized_value, confidence, check_status, raw_result_json)
VALUES (?, ?, ?, ?, ?, ?, ?, ?)`,
			taskID, fileID, rule.FieldCode, rule.FieldName, value, result.Confidence, status, rawJSON).Error
	}
	if hasIssue {
		return "manual_review"
	}
	return "ocr_passed"
}

func (h *PhotoHandler) writeEmptyOCRResults(taskID int64, fileID int64, rules []ocrFieldRuleRow, status string, message string) error {
	raw, _ := json.Marshal(gin.H{"error": message})
	_ = h.db.Exec("DELETE FROM machine_photo_ocr_results WHERE task_id = ?", taskID).Error
	if len(rules) == 0 {
		return h.db.Exec(`
INSERT INTO machine_photo_ocr_results
  (task_id, file_id, field_code, field_name, recognized_value, confidence, check_status, raw_result_json)
VALUES (?, ?, 'recognized_text', '识别文本', '', 0, ?, ?)`,
			taskID, fileID, status, string(raw)).Error
	}
	for _, rule := range rules {
		if err := h.db.Exec(`
INSERT INTO machine_photo_ocr_results
  (task_id, file_id, field_code, field_name, recognized_value, confidence, check_status, raw_result_json)
VALUES (?, ?, ?, ?, '', 0, ?, ?)`,
			taskID, fileID, rule.FieldCode, rule.FieldName, status, string(raw)).Error; err != nil {
			return err
		}
	}
	return nil
}

func (h *PhotoHandler) syncComponentBindingFromTaskID(taskID int64) error {
	if taskID <= 0 {
		return nil
	}
	result := h.db.Exec(`
INSERT INTO machine_component_bindings
  (binding_key, machine_no, machine_batch_no, model_name, customer, agent, machine_status, location_code,
   delivery_date, outbound_at, material_code, material_name, material_type, material_spec, component_serial_no, instance_batch_no,
   instance_flow_no, position_code, position_name, bound_at, active, source, source_task_id, source_file_id,
   source_ocr_result_id, file_name, recognized_value, manual_value, confidence, check_status, reviewed_by, reviewed_at)
SELECT
  CONCAT('V8-', t.serial_no, '-', t.position_code) AS binding_key,
  t.serial_no AS machine_no,
  COALESCE(fg.`+"`批次号`"+`, '') AS machine_batch_no,
  t.model_name,
  COALESCE(fg.`+"`客户`"+`, '') AS customer,
  COALESCE(fg.`+"`代理商`"+`, '') AS agent,
  COALESCE(fg.`+"`状态`"+`, '') AS machine_status,
  COALESCE(fg.`+"`Location_Code`"+`, '') AS location_code,
  CASE
    WHEN sh.outbound_at IS NOT NULL THEN DATE(sh.outbound_at)
    WHEN TRIM(COALESCE(fg.`+"`状态`"+`, '')) LIKE '已出库%' THEN DATE(fg.`+"`更新时间`"+`)
    ELSE NULL
  END AS delivery_date,
  CASE
    WHEN sh.outbound_at IS NOT NULL THEN sh.outbound_at
    WHEN TRIM(COALESCE(fg.`+"`状态`"+`, '')) LIKE '已出库%' THEN fg.`+"`更新时间`"+`
    ELSE NULL
  END AS outbound_at,
  LEFT(CONCAT(t.position_code, '-', TRIM(COALESCE(NULLIF(r.manual_value, ''), r.recognized_value, ''))), 80) AS material_code,
  t.item_name AS material_name,
  COALESCE(NULLIF(pil.item_category, ''), '编号') AS material_type,
  t.position_code AS material_spec,
  LEFT(TRIM(COALESCE(NULLIF(r.manual_value, ''), r.recognized_value, '')), 100) AS component_serial_no,
  '' AS instance_batch_no,
  '' AS instance_flow_no,
  t.position_code,
  t.item_name AS position_name,
  DATE(COALESCE(r.reviewed_at, f.uploaded_at, t.updated_at, NOW())) AS bound_at,
  1 AS active,
  CASE
    WHEN JSON_UNQUOTE(JSON_EXTRACT(r.raw_result_json, '$.source')) = 'qr_static' THEN 'V8_QR'
    ELSE 'V8_OCR'
  END AS source,
  t.id AS source_task_id,
  r.file_id AS source_file_id,
  r.id AS source_ocr_result_id,
  COALESCE(f.file_name, '') AS file_name,
  r.recognized_value,
  r.manual_value,
  r.confidence,
  r.check_status,
  COALESCE(r.reviewed_by, '') AS reviewed_by,
  r.reviewed_at
FROM machine_photo_tasks t
JOIN (
  SELECT task_id, MAX(id) AS result_id
  FROM machine_photo_ocr_results
  WHERE check_status = 'manual_passed'
    AND TRIM(COALESCE(NULLIF(manual_value, ''), recognized_value, '')) <> ''
    AND task_id = ?
  GROUP BY task_id
) latest ON latest.task_id = t.id
JOIN machine_photo_ocr_results r ON r.id = latest.result_id
LEFT JOIN machine_photo_files f ON f.id = r.file_id
LEFT JOIN photo_item_library pil ON pil.position_code = t.position_code
LEFT JOIN finished_goods_data fg ON TRIM(fg.`+"`流水号`"+`) = t.serial_no
LEFT JOIN (
  SELECT TRIM(`+"`流水号`"+`) AS serial_no, MAX(`+"`更新时间`"+`) AS outbound_at
  FROM shipping_history
  WHERE TRIM(COALESCE(`+"`状态`"+`, '')) LIKE '已出库%'
  GROUP BY TRIM(`+"`流水号`"+`)
) sh ON sh.serial_no = t.serial_no
WHERE t.id = ?
  AND t.enabled = 1
  AND t.status IN ('manual_passed', 'completed')
ON DUPLICATE KEY UPDATE
  machine_batch_no = VALUES(machine_batch_no),
  model_name = VALUES(model_name),
  customer = VALUES(customer),
  agent = VALUES(agent),
  machine_status = VALUES(machine_status),
  location_code = VALUES(location_code),
  delivery_date = VALUES(delivery_date),
  outbound_at = VALUES(outbound_at),
  material_code = VALUES(material_code),
  material_name = VALUES(material_name),
  material_type = VALUES(material_type),
  material_spec = VALUES(material_spec),
  component_serial_no = VALUES(component_serial_no),
  instance_batch_no = VALUES(instance_batch_no),
  instance_flow_no = VALUES(instance_flow_no),
  position_name = VALUES(position_name),
  bound_at = VALUES(bound_at),
  active = VALUES(active),
  source = VALUES(source),
  source_task_id = VALUES(source_task_id),
  source_file_id = VALUES(source_file_id),
  source_ocr_result_id = VALUES(source_ocr_result_id),
  file_name = VALUES(file_name),
  recognized_value = VALUES(recognized_value),
  manual_value = VALUES(manual_value),
  confidence = VALUES(confidence),
  check_status = VALUES(check_status),
  reviewed_by = VALUES(reviewed_by),
  reviewed_at = VALUES(reviewed_at),
  updated_at = CURRENT_TIMESTAMP`, taskID, taskID)
	if result.Error != nil {
		return result.Error
	}
	if result.RowsAffected == 0 {
		return h.db.Table("machine_component_bindings").
			Where("source_task_id = ?", taskID).
			Updates(map[string]interface{}{"active": false}).Error
	}
	return nil
}

func recognizedOCRValue(result ocrServiceField) string {
	value := strings.TrimSpace(result.RecognizedValue)
	if value == "" {
		value = strings.TrimSpace(result.Value)
	}
	return value
}

func firstNonZero(value int, fallback int) int {
	if value != 0 {
		return value
	}
	return fallback
}

func (h *PhotoHandler) savePhotoItemsRows(rows []photoItemRow) error {
	tx := h.db.Begin()
	for i, row := range rows {
		code := strings.ToUpper(strings.TrimSpace(row.PositionCode))
		name := strings.TrimSpace(row.ItemName)
		if code == "" || name == "" {
			tx.Rollback()
			return fmt.Errorf("位置编码和拍照项目名称不能为空")
		}
		if row.DefaultOCREnabled && strings.TrimSpace(row.DefaultOCRProfile) == "" {
			tx.Rollback()
			return fmt.Errorf("启用OCR时必须填写OCR方案: %s", code)
		}
		if err := tx.Exec(`
INSERT INTO photo_item_library
  (position_code, item_name, item_category, shooting_requirement, default_required, default_ocr_enabled, default_ocr_profile, sort_order, enabled)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
ON DUPLICATE KEY UPDATE
  item_name = VALUES(item_name),
  item_category = VALUES(item_category),
  shooting_requirement = VALUES(shooting_requirement),
  default_required = VALUES(default_required),
  default_ocr_enabled = VALUES(default_ocr_enabled),
  default_ocr_profile = VALUES(default_ocr_profile),
  sort_order = VALUES(sort_order),
  enabled = VALUES(enabled),
  updated_at = CURRENT_TIMESTAMP`,
			code,
			name,
			strings.TrimSpace(row.ItemCategory),
			strings.TrimSpace(row.ShootingRequirement),
			row.DefaultRequired,
			row.DefaultOCREnabled,
			strings.TrimSpace(row.DefaultOCRProfile),
			firstNonZero(row.SortOrder, i+1),
			row.Enabled,
		).Error; err != nil {
			tx.Rollback()
			return err
		}
	}
	return tx.Commit().Error
}

func safeName(value string) string {
	replacer := strings.NewReplacer("\\", "_", "/", "_", ":", "_", "*", "_", "?", "_", "\"", "_", "<", "_", ">", "_", "|", "_", " ", "_")
	return replacer.Replace(strings.TrimSpace(value))
}

func removeLocalTaskFile(path string) error {
	cleanPath := filepath.Clean(strings.TrimSpace(path))
	if cleanPath == "." || cleanPath == "" {
		return nil
	}
	target := cleanPath
	if !filepath.IsAbs(target) {
		absTarget, err := filepath.Abs(target)
		if err != nil {
			return err
		}
		target = absTarget
	}
	cwd, err := os.Getwd()
	if err != nil {
		return err
	}
	absCwd, err := filepath.Abs(cwd)
	if err != nil {
		return err
	}
	rel, err := filepath.Rel(absCwd, target)
	if err != nil {
		return err
	}
	if strings.HasPrefix(rel, "..") || filepath.IsAbs(rel) {
		return fmt.Errorf("refuse to remove file outside workspace: %s", path)
	}
	if err := os.Remove(target); err != nil && !os.IsNotExist(err) {
		return err
	}
	return nil
}

func taskHasPhoto(task machinePhotoTaskRow) bool {
	return strings.TrimSpace(task.FileName) != "" || task.FileID != nil
}

func taskHasConfirmedOCR(task machinePhotoTaskRow) bool {
	for _, result := range task.OCRResults {
		if strings.TrimSpace(result.CheckStatus) != "manual_passed" {
			continue
		}
		value := strings.TrimSpace(result.ManualValue)
		if value == "" {
			value = strings.TrimSpace(result.RecognizedValue)
		}
		if value != "" {
			return true
		}
	}
	return false
}

func maxInt(value int, floor int) int {
	if value < floor {
		return floor
	}
	return value
}

func intFromSummary(summary gin.H, key string) int {
	switch value := summary[key].(type) {
	case int:
		return value
	case int64:
		return int(value)
	case float64:
		return int(value)
	default:
		return 0
	}
}

func taskStatusSubmittable(status string) bool {
	switch strings.TrimSpace(status) {
	case "completed", "ocr_passed", "manual_passed", "skipped":
		return true
	default:
		return false
	}
}

func normalizeTaskStatus(status string) string {
	switch strings.TrimSpace(status) {
	case "completed", "ocr_passed", "manual_passed", "manual_review", "retake_required", "skipped":
		return strings.TrimSpace(status)
	default:
		return ""
	}
}
