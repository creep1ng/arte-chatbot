#!/bin/bash
# Script para crear el role IAM necesario para GitHub Actions OIDC
# Ejecutar con: ./scripts/setup-github-oidc.sh

set -e

AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query 'Account' --output text)
GITHUB_REPO="creep1ng/arte-chatbot"
OIDC_PROVIDER_URL="token.actions.githubusercontent.com"

echo "Configurando OIDC para GitHub Actions en cuenta AWS: $AWS_ACCOUNT_ID"

# Crear el role IAM
cat > /tmp/github-actions-role-policy.json << EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Federated": "arn:aws:iam::${AWS_ACCOUNT_ID}:oidc-provider/token.actions.githubusercontent.com"
      },
      "Action": "sts:AssumeRoleWithWebIdentity",
      "Condition": {
        "StringEquals": {
          "token.actions.githubusercontent.com:aud": "sts.amazonaws.com"
        },
        "StringLike": {
          "token.actions.githubusercontent.com:sub": "repo:${GITHUB_REPO}:*"
        }
      }
    }
  ]
}
EOF

aws iam create-role \
  --role-name arte-chatbot-github-actions \
  --assume-role-policy-document file:///tmp/github-actions-role-policy.json \
  --description "Role for GitHub Actions to deploy Arte Chatbot"

# Crear y adjuntar la política de permisos
cat > /tmp/github-actions-permissions-policy.json << 'EOF'
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
      "Action": [
        "iam:PassRole"
      ],
      "Resource": "*",
      "Condition": {
        "StringLike": {
          "iam:PassedToService": "ecs-tasks.amazonaws.com"
        }
      }
    },
    {
      "Effect": "Allow",
      "Action": [
        "logs:CreateLogGroup",
        "logs:CreateLogStream",
        "logs:PutLogEvents"
      ],
      "Resource": "arn:aws:logs:*:*:*"
    }
  ]
}
EOF

aws iam create-policy \
  --policy-name arte-chatbot-github-actions \
  --policy-document file:///tmp/github-actions-permissions-policy.json

aws iam attach-role-policy \
  --role-name arte-chatbot-github-actions \
  --policy-arn "arn:aws:iam::${AWS_ACCOUNT_ID}:policy/arte-chatbot-github-actions"

echo ""
echo "Role IAM creado exitosamente!"
echo ""
echo "Configurar en GitHub Secrets:"
echo "  AWS_ROLE_ARN = arn:aws:iam::${AWS_ACCOUNT_ID}:role/arte-chatbot-github-actions"