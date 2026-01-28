# ==============================================================================
# PostgreSQL Client Pod (用于数据库调试)
# ==============================================================================
# 使用方式:
#   1. 直接连接数据库:
#      kubectl exec -it -n auth-platform deploy/postgres-client -- psql -h $PGHOST -U $PGUSER -d $PGDATABASE
#   2. 通过 socat 端口转发:
#      kubectl port-forward -n auth-platform svc/postgres-client 5432:5432
#      然后本地: psql -h localhost -p 5432 -U <username> -d <database>

resource "kubernetes_deployment" "postgres_client" {
  count = var.enable_db_client ? 1 : 0

  metadata {
    name      = "postgres-client"
    namespace = "auth-platform"

    labels = {
      app                            = "postgres-client"
      "app.kubernetes.io/name"       = "postgres-client"
      "app.kubernetes.io/managed-by" = "terraform"
    }
  }

  spec {
    replicas = 1

    selector {
      match_labels = {
        app = "postgres-client"
      }
    }

    template {
      metadata {
        labels = {
          app = "postgres-client"
        }
      }

      spec {
        container {
          name  = "postgres-client"
          image = "alpine:3.19"

          command = ["/bin/sh", "-c"]
          args = [
            <<-EOT
            apk add --no-cache postgresql-client socat
            echo "PostgreSQL client ready. Aurora endpoint: $PGHOST:$PGPORT"
            echo "Use: psql -h $PGHOST -U $PGUSER -d $PGDATABASE"
            echo ""
            echo "Starting socat proxy on port 5432..."
            socat TCP-LISTEN:5432,fork,reuseaddr TCP:$PGHOST:$PGPORT
            EOT
          ]

          port {
            container_port = 5432
            protocol       = "TCP"
          }

          env {
            name = "PGHOST"
            value_from {
              secret_key_ref {
                name = "user-service-secret"
                key  = "DB_HOST"
              }
            }
          }

          env {
            name  = "PGPORT"
            value = "5432"
          }

          env {
            name  = "PGDATABASE"
            value = "auth_platform"
          }

          env {
            name = "PGUSER"
            value_from {
              secret_key_ref {
                name = "user-service-secret"
                key  = "DB_USERNAME"
              }
            }
          }

          env {
            name = "PGPASSWORD"
            value_from {
              secret_key_ref {
                name = "user-service-secret"
                key  = "DB_PASSWORD"
              }
            }
          }

          resources {
            requests = {
              cpu    = "50m"
              memory = "64Mi"
            }
            limits = {
              cpu    = "100m"
              memory = "128Mi"
            }
          }
        }
      }
    }
  }
}

resource "kubernetes_service" "postgres_client" {
  count = var.enable_db_client ? 1 : 0

  metadata {
    name      = "postgres-client"
    namespace = "auth-platform"

    labels = {
      app                            = "postgres-client"
      "app.kubernetes.io/name"       = "postgres-client"
      "app.kubernetes.io/managed-by" = "terraform"
    }
  }

  spec {
    selector = {
      app = "postgres-client"
    }

    port {
      name        = "postgresql"
      port        = 5432
      target_port = 5432
      protocol    = "TCP"
    }

    type = "ClusterIP"
  }
}
