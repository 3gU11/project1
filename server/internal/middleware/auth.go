package middleware

import (
	"net/http"
	"strings"

	"github.com/gin-gonic/gin"
	"gorm.io/gorm"
)

func AdminOnly(db *gorm.DB) gin.HandlerFunc {
	return func(c *gin.Context) {
		username := c.GetHeader("X-Username")
		role := strings.ToLower(c.GetHeader("X-Role"))
		if username == "" || role == "" {
			// Try token-based auth
			username, role = extractFromToken(c)
		}

		role = strings.ToLower(strings.TrimSpace(role))
		if role != "admin" && role != "boss" {
			c.AbortWithStatusJSON(http.StatusForbidden, gin.H{"error": "forbidden: admin or boss role required"})
			return
		}

		c.Set("username", strings.TrimSpace(username))
		c.Set("role", role)
		c.Next()
	}
}

func extractFromToken(c *gin.Context) (string, string) {
	auth := c.GetHeader("Authorization")
	if auth == "" {
		return "", ""
	}
	token := strings.TrimPrefix(auth, "Bearer ")
	if token == auth {
		return "", ""
	}
	// Simple token parsing - in production use JWT validation
	// For dev/demo, accept a plain user:role token
	parts := strings.SplitN(token, ":", 2)
	if len(parts) == 2 {
		return parts[0], parts[1]
	}
	return token, ""
}

// CORS middleware for development
func CORS(allowOrigins string) gin.HandlerFunc {
	return func(c *gin.Context) {
		origin := c.GetHeader("Origin")
		if origin == "" {
			origin = allowOrigins
		}
		c.Header("Access-Control-Allow-Origin", origin)
		c.Header("Access-Control-Allow-Methods", "GET, POST, PUT, PATCH, DELETE, OPTIONS")
		c.Header("Access-Control-Allow-Headers", "Content-Type, Authorization, X-Username, X-Role")
		c.Header("Access-Control-Allow-Credentials", "true")
		if c.Request.Method == "OPTIONS" {
			c.AbortWithStatus(204)
			return
		}
		c.Next()
	}
}

// AuthMiddleware validates any authenticated user
func AuthMiddleware(db *gorm.DB) gin.HandlerFunc {
	return func(c *gin.Context) {
		username := c.GetHeader("X-Username")
		role := strings.ToLower(c.GetHeader("X-Role"))
		if username == "" || role == "" {
			username, role = extractFromToken(c)
		}
		if username == "" {
			c.AbortWithStatusJSON(http.StatusUnauthorized, gin.H{"error": "authentication required"})
			return
		}
		c.Set("username", strings.TrimSpace(username))
		c.Set("role", strings.ToLower(strings.TrimSpace(role)))
		c.Next()
	}
}

// RequireRegion checks if the user has access to a given region
func RequireRegion(db *gorm.DB) gin.HandlerFunc {
	return func(c *gin.Context) {
		region := c.Query("region")
		if region == "" {
			region = c.GetHeader("X-Region")
		}
		if region == "" {
			c.Next()
			return
		}

		usernameObj, exists := c.Get("username")
		if !exists {
			c.AbortWithStatusJSON(http.StatusForbidden, gin.H{"error": "region check requires auth"})
			return
		}
		username := usernameObj.(string)

		var user struct{ Region string }
		err := db.Table("users").Select("region").Where("username = ? OR openid = ?", username, username).First(&user).Error
		if err != nil {
			c.Next() // User not in DB, allow passthrough for dev
			return
		}
		if user.Region != "" && !strings.EqualFold(user.Region, region) {
			c.AbortWithStatusJSON(http.StatusForbidden, gin.H{"error": "region access denied"})
			return
		}
		c.Next()
	}
}
