package handler

import (
	"fmt"
	"net/http"
	"os"
	"strings"

	"github.com/gin-gonic/gin"
	"github.com/golang-jwt/jwt/v5"
)

func JWTAuthFromEnvironment() (gin.HandlerFunc, error) {
	secret := strings.TrimSpace(os.Getenv("JWT_SECRET_KEY"))
	if secret == "" {
		return nil, fmt.Errorf("JWT_SECRET_KEY is required")
	}
	return JWTAuth([]byte(secret)), nil
}

func JWTAuth(secret []byte) gin.HandlerFunc {
	return func(c *gin.Context) {
		authHeader := c.GetHeader("Authorization")
		queryToken := strings.TrimSpace(c.Query("token"))
		tokenValue := queryToken
		if authHeader != "" {
			parts := strings.SplitN(authHeader, " ", 2)
			if len(parts) != 2 || !strings.EqualFold(parts[0], "bearer") || strings.TrimSpace(parts[1]) == "" {
				c.AbortWithStatusJSON(http.StatusUnauthorized, gin.H{"error": "invalid Authorization format"})
				return
			}
			tokenValue = strings.TrimSpace(parts[1])
			if queryToken != "" && queryToken != tokenValue {
				c.AbortWithStatusJSON(http.StatusUnauthorized, gin.H{"error": "conflicting authentication tokens"})
				return
			}
		}
		if tokenValue == "" {
			c.AbortWithStatusJSON(http.StatusUnauthorized, gin.H{"error": "missing authentication token"})
			return
		}

		token, err := jwt.Parse(tokenValue, func(t *jwt.Token) (interface{}, error) {
			if t.Method.Alg() != jwt.SigningMethodHS256.Alg() {
				return nil, jwt.ErrSignatureInvalid
			}
			return secret, nil
		})
		if err != nil || !token.Valid {
			c.AbortWithStatusJSON(http.StatusUnauthorized, gin.H{"error": "invalid token"})
			return
		}

		c.Next()
	}
}
