package handler

import (
	"log"
	"net/http"

	"github.com/gin-gonic/gin"
)

const maxConcurrentBimgOps = 8

var bimgSem = make(chan struct{}, maxConcurrentBimgOps)

func acquireBimg() {
	bimgSem <- struct{}{}
}

func releaseBimg() {
	<-bimgSem
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
