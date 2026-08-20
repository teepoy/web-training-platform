package handler

import "github.com/gin-gonic/gin"

// SafeRequestLogger deliberately excludes the query string because browser
// image requests carry their JWT in a query parameter.
func SafeRequestLogger() gin.HandlerFunc {
	return gin.LoggerWithConfig(gin.LoggerConfig{SkipQueryString: true})
}
