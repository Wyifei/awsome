# syntax=docker/dockerfile:1
# Profile Service

# ============== Builder Stage ==============
FROM public.ecr.aws/docker/library/amazoncorretto:21-alpine AS builder
WORKDIR /app

# Copy pre-built JAR
COPY target/profile-service-*.jar app.jar

# ============== Runtime Stage ==============
FROM public.ecr.aws/docker/library/amazoncorretto:21-alpine AS runtime
WORKDIR /app

# Apply security updates and create non-root user
RUN apk update && \
    apk upgrade --no-cache && \
    apk add --no-cache wget && \
    addgroup -S appgroup && adduser -S appuser -G appgroup && \
    rm -rf /var/cache/apk/*

# Copy JAR from builder
COPY --from=builder /app/app.jar app.jar

# Switch to non-root user
USER appuser

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=3s --start-period=60s --retries=3 \
    CMD wget -q --spider http://localhost:8080/actuator/health || exit 1

ENTRYPOINT ["java", "-XX:+UseContainerSupport", "-XX:MaxRAMPercentage=75.0", "-jar", "app.jar"]
