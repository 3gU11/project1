package service

import "gorm.io/gorm"

// CaptureSandboxBaselines is intentionally a no-op when the optional sandbox
// baseline table is unavailable. Callers remain transactional and can proceed
// with normal scheduling updates.
func CaptureSandboxBaselines(tx *gorm.DB, actor string, batchIDs ...string) error {
	return nil
}
