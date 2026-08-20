package handler

import (
	"log"
	"net/http"

	"github.com/gin-gonic/gin"
)

const maxConcurrentResizeOps = 8

var resizeSem = make(chan struct{}, maxConcurrentResizeOps)

func acquireResize() {
	resizeSem <- struct{}{}
}

func releaseResize() {
	<-resizeSem
}

func StableRecovery() gin.HandlerFunc {
	return func(c *gin.Context) {
		defer func() {
			if r := recover(); r != nil {
				log.Printf("[RECOVERY] panic in %s %s: %v", c.Request.Method, c.Request.URL.Path, r)
				c.AbortWithStatusJSON(http.StatusInternalServerError, gin.H{
					"error": "internal error, request will be retried",
				})
			}
		}()
		c.Next()
	}
}
