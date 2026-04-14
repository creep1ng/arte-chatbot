# Infrastructure - AWS Deployment

## Recursos Desplegados

Este módulo de Terraform despliega la siguiente infraestructura en AWS:

- **VPC** con subredes públicas y privadas
- **ECS Cluster** con Fargate para el backend
- **Application Load Balancer** para routing
- **ECR Repository** para imágenes Docker del backend
- **S3 Bucket** para hosting estático del frontend
- **Security Groups** para ECS, ALB, RDS y ElastiCache (preparado para futuro)
- **IAM Roles** para ejecución de tareas ECS

## Pre-requisitos

1. **AWS CLI** configurada con credenciales de administrador
2. **Terraform** >= 1.6.0
3. **Bucket S3** para guardar estado de Terraform (crear manualmente):
   ```bash
   aws s3 mb s3://arte-chatbot-terraform-state --region us-east-1
   ```

## Comandos

### Inicializar Terraform
```bash
cd infrastructure
terraform init
```

### Plan de cambios
```bash
terraform plan -var="frontend_bucket_name=tu-bucket-unico"
```

### Aplicar cambios
```bash
terraform apply -var="frontend_bucket_name=tu-bucket-unico"
```

### Destruir recursos (CUIDADO)
```bash
terraform destroy
```

## GitHub Actions Secrets

Configurar los siguientes secrets en el repositorio de GitHub:

| Secret | Descripción |
|--------|-------------|
| `AWS_ROLE_ARN` | ARN del role IAM para GitHub Actions (ej: `arn:aws:iam::123456789:role/github-actions-role`) |
| `BACKEND_API_URL` | URL del backend (ej: `https://api.tudominio.com`) |

## IAM Role para GitHub Actions

Crear un role IAM con la siguiente política trust para OIDC:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Federated": "arn:aws:iam::123456789:oidc-provider/token.actions.githubusercontent.com"
      },
      "Action": "sts:AssumeRoleWithWebIdentity",
      "Condition": {
        "StringEquals": {
          "token.actions.githubusercontent.com:aud": "sts.amazonaws.com"
        },
        "StringLike": {
          "token.actions.githubusercontent.com:sub": "repo:creep1ng/arte-chatbot:*"
        }
      }
    }
  ]
}
```

Y adjuntar la política de permisos:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "ecr:GetAuthorizationToken",
        "ecr:BatchCheckLayerAvailability",
        "ecr:GetDownloadUrlForLayer",
        "ecr:BatchGetImage",
        "ecs:DescribeTaskDefinition",
        "ecs:RegisterTaskDefinition",
        "ecs:UpdateService",
        "ecs:DescribeServices",
        "s3:PutObject",
        "s3:GetObject",
        "s3:DeleteObject",
        "s3:ListBucket"
      ],
      "Resource": "*"
    },
    {
      "Effect": "Allow",
      "Action": "sts:AssumeRole",
      "Resource": "*"
    }
  ]
}
```

## Preparación para RDS y ElastiCache

Los Security Groups para RDS (puerto 5432) y ElastiCache (puerto 6379) ya están creados. Para habilitar PostgreSQL y Redis:

1. Descomentar los bloques de recursos en `main.tf`
2. Añadir variables `rds_username` y `rds_password` en `variables.tf`
3. Ejecutar `terraform apply`
4. Actualizar la task definition de ECS con las variables de entorno de conexión