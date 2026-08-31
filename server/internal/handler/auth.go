package handler

import (
	"net/http"
	"strings"

	"github.com/gin-gonic/gin"
	"gorm.io/gorm"
)

type AuthHandler struct {
	db *gorm.DB
}

func NewAuthHandler(db *gorm.DB) *AuthHandler {
	return &AuthHandler{db: db}
}

type loginUser struct {
	Username string `json:"username"`
	Password string `json:"password"`
	Role     string `json:"role"`
	Name     string `json:"name"`
	Region   string `json:"region"`
}

func (h *AuthHandler) Login(c *gin.Context) {
	var req struct {
		Username string `json:"username" binding:"required"`
		Password string `json:"password" binding:"required"`
	}
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "username and password required"})
		return
	}

	var user loginUser
	err := h.db.Raw(`
		SELECT
			username,
			password,
			COALESCE(role, 'viewer') AS role,
			COALESCE(name, username) AS name,
			'' AS region
		FROM users
		WHERE username = ?
		  AND (status IS NULL OR status = '' OR status = 'active')
		LIMIT 1`, req.Username).Scan(&user).Error
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}
	if user.Username == "" || user.Password != req.Password {
		c.JSON(http.StatusUnauthorized, gin.H{"error": "invalid credentials"})
		return
	}

	role := strings.ToLower(strings.TrimSpace(user.Role))
	c.JSON(http.StatusOK, gin.H{
		"token": user.Username + ":" + role,
		"user": gin.H{
			"username": user.Username,
			"role":     role,
			"name":     user.Name,
			"region":   user.Region,
		},
	})
}

func (h *AuthHandler) Me(c *gin.Context) {
	username := c.GetString("username")
	role := c.GetString("role")
	if username == "" {
		c.JSON(http.StatusUnauthorized, gin.H{"error": "authentication required"})
		return
	}
	c.JSON(http.StatusOK, gin.H{
		"user": gin.H{
			"username": username,
			"role":     role,
		},
	})
}
