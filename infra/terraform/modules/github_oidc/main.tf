locals {
  production_github_subject = "repo:${var.github_owner}/${var.github_repository}:ref:refs/heads/${var.branch}"
  preview_github_subject    = "repo:${var.github_owner}/${var.github_repository}:pull_request"
  ssm_deploy_resources      = concat(var.ssm_instance_arns, var.ssm_document_arns)
  lambda_deploy_arns = distinct(concat(
    var.lambda_function_arns,
    [for arn in var.lambda_function_arns : "${arn}:*"],
    var.lambda_alias_arns,
  ))

  preview_lambda_arns = [
    "arn:${data.aws_partition.current.partition}:lambda:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:function:${var.preview_resource_prefix}-*",
  ]
  preview_table_arns = [
    "arn:${data.aws_partition.current.partition}:dynamodb:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:table/${var.preview_resource_prefix}-*",
    "arn:${data.aws_partition.current.partition}:dynamodb:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:table/${var.preview_resource_prefix}-*/index/*",
  ]
  preview_log_arns = [
    "arn:${data.aws_partition.current.partition}:logs:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:log-group:/aws/lambda/${var.preview_resource_prefix}-*:*",
    "arn:${data.aws_partition.current.partition}:logs:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:log-group:/aws/apigateway/${var.preview_resource_prefix}-*:*",
  ]
  preview_ssm_secret_arns = [
    "arn:${data.aws_partition.current.partition}:ssm:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:parameter/arte-chatbot/pr-preview/*",
  ]
  preview_secrets_manager_arns = [
    "arn:${data.aws_partition.current.partition}:secretsmanager:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:secret:/arte-chatbot/pr-preview/*",
  ]
}

data "aws_partition" "current" {}
data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

resource "aws_iam_openid_connect_provider" "github" {
  url            = "https://token.actions.githubusercontent.com"
  client_id_list = ["sts.amazonaws.com"]
  thumbprint_list = [
    "6938fd4d98bab03faadb97b34396831e3780aea1",
  ]
  tags = var.tags
}

data "aws_iam_policy_document" "production_assume_role" {
  statement {
    actions = ["sts:AssumeRoleWithWebIdentity"]
    principals {
      type        = "Federated"
      identifiers = [aws_iam_openid_connect_provider.github.arn]
    }
    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values   = ["sts.amazonaws.com"]
    }
    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:sub"
      values   = [local.production_github_subject]
    }
  }
}

data "aws_iam_policy_document" "preview_assume_role" {
  statement {
    actions = ["sts:AssumeRoleWithWebIdentity"]
    principals {
      type        = "Federated"
      identifiers = [aws_iam_openid_connect_provider.github.arn]
    }
    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values   = ["sts.amazonaws.com"]
    }
    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:sub"
      values   = [local.preview_github_subject]
    }
  }
}

data "aws_iam_policy_document" "preview_lambda_assume_role" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "this" {
  name               = var.role_name
  assume_role_policy = data.aws_iam_policy_document.production_assume_role.json
  tags               = var.tags
}

resource "aws_iam_role" "preview" {
  name               = var.preview_role_name
  assume_role_policy = data.aws_iam_policy_document.preview_assume_role.json
  tags               = merge(var.tags, { Environment = "pr-preview" })
}

data "aws_iam_policy_document" "deploy" {
  statement {
    sid       = "EcrAuthorization"
    actions   = ["ecr:GetAuthorizationToken"]
    resources = ["*"]
  }
  statement {
    sid = "EcrPromotion"
    actions = [
      "ecr:BatchCheckLayerAvailability", "ecr:BatchGetImage",
      "ecr:CompleteLayerUpload", "ecr:DescribeImages",
      "ecr:DescribeRepositories", "ecr:GetDownloadUrlForLayer",
      "ecr:InitiateLayerUpload", "ecr:PutImage", "ecr:UploadLayerPart",
    ]
    resources = var.ecr_repository_arns
  }
  dynamic "statement" {
    for_each = length(local.ssm_deploy_resources) > 0 ? [1] : []
    content {
      sid       = "SsmDeployCommand"
      actions   = ["ssm:SendCommand"]
      resources = local.ssm_deploy_resources
    }
  }
  dynamic "statement" {
    for_each = length(local.ssm_deploy_resources) > 0 ? [1] : []
    content {
      sid = "SsmDeployStatusReads"
      actions = [
        "ssm:GetCommandInvocation", "ssm:DescribeInstanceInformation",
        "ssm:ListCommandInvocations", "ssm:ListCommands",
      ]
      resources = ["*"]
    }
  }
  dynamic "statement" {
    for_each = length(local.lambda_deploy_arns) > 0 ? [1] : []
    content {
      sid = "LambdaPackagePromotion"
      actions = [
        "lambda:GetAlias", "lambda:GetFunction", "lambda:PublishVersion",
        "lambda:UpdateAlias", "lambda:UpdateFunctionCode",
      ]
      resources = local.lambda_deploy_arns
    }
  }
  dynamic "statement" {
    for_each = length(var.state_table_arns) > 0 ? [1] : []
    content {
      sid       = "ReadSmokeStateTable"
      actions   = ["dynamodb:DescribeTable", "dynamodb:GetItem", "dynamodb:Query"]
      resources = var.state_table_arns
    }
  }
  dynamic "statement" {
    for_each = length(var.secret_arns) > 0 ? [1] : []
    content {
      sid       = "ReadDeploymentSecretMetadata"
      actions   = ["secretsmanager:DescribeSecret", "ssm:GetParameters"]
      resources = var.secret_arns
    }
  }
}

resource "aws_iam_role_policy" "deploy" {
  name   = "${var.role_name}-deploy"
  role   = aws_iam_role.this.id
  policy = data.aws_iam_policy_document.deploy.json
}

# This boundary is managed by the production foundation, not pull-request
# Terraform. Preview code cannot expand the Lambda role's effective access.
data "aws_iam_policy_document" "preview_lambda_boundary" {
  statement {
    sid       = "WritePreviewLogs"
    actions   = ["logs:CreateLogStream", "logs:PutLogEvents"]
    resources = local.preview_log_arns
  }
  statement {
    sid       = "ReadCatalogObjects"
    actions   = ["s3:GetObject"]
    resources = [for bucket in var.preview_catalog_bucket_names : "arn:${data.aws_partition.current.partition}:s3:::${bucket}/*"]
  }
  statement {
    sid       = "ListCatalogBuckets"
    actions   = ["s3:ListBucket"]
    resources = [for bucket in var.preview_catalog_bucket_names : "arn:${data.aws_partition.current.partition}:s3:::${bucket}"]
  }
  statement {
    sid = "UsePreviewStateTables"
    actions = [
      "dynamodb:BatchGetItem", "dynamodb:BatchWriteItem",
      "dynamodb:ConditionCheckItem", "dynamodb:DeleteItem",
      "dynamodb:DescribeTable", "dynamodb:GetItem", "dynamodb:PutItem",
      "dynamodb:Query", "dynamodb:UpdateItem",
    ]
    resources = local.preview_table_arns
  }
  statement {
    sid       = "ReadPreviewSsmSecrets"
    actions   = ["ssm:GetParameter", "ssm:GetParameters"]
    resources = local.preview_ssm_secret_arns
  }
  statement {
    sid       = "ReadPreviewSecretsManagerSecrets"
    actions   = ["secretsmanager:GetSecretValue"]
    resources = local.preview_secrets_manager_arns
  }
  dynamic "statement" {
    for_each = length(var.preview_kms_key_arns) > 0 ? [1] : []
    content {
      sid       = "DecryptPreviewSecrets"
      actions   = ["kms:Decrypt"]
      resources = var.preview_kms_key_arns
    }
  }
}

resource "aws_iam_policy" "preview_lambda_boundary" {
  name        = "${var.preview_resource_prefix}-lambda-boundary"
  description = "Maximum runtime permissions for pull-request preview Lambdas."
  policy      = data.aws_iam_policy_document.preview_lambda_boundary.json
  tags        = merge(var.tags, { Environment = "pr-preview" })
}

resource "aws_iam_role" "preview_lambda" {
  name                 = "${var.preview_resource_prefix}-lambda-runtime"
  assume_role_policy   = data.aws_iam_policy_document.preview_lambda_assume_role.json
  permissions_boundary = aws_iam_policy.preview_lambda_boundary.arn
  tags                 = merge(var.tags, { Environment = "pr-preview" })
}

resource "aws_iam_role_policy_attachment" "preview_lambda_runtime" {
  role       = aws_iam_role.preview_lambda.name
  policy_arn = aws_iam_policy.preview_lambda_boundary.arn
}

data "aws_iam_policy_document" "preview_deploy" {
  statement {
    sid       = "ReadCallerIdentity"
    actions   = ["sts:GetCallerIdentity"]
    resources = ["*"]
  }
  statement {
    sid       = "UsePreviewTerraformState"
    actions   = ["s3:DeleteObject", "s3:GetObject", "s3:PutObject"]
    resources = ["arn:${data.aws_partition.current.partition}:s3:::${var.preview_state_bucket_name}/${var.preview_state_key_prefix}/*"]
  }
  statement {
    sid       = "ListPreviewTerraformState"
    actions   = ["s3:GetBucketLocation", "s3:ListBucket"]
    resources = ["arn:${data.aws_partition.current.partition}:s3:::${var.preview_state_bucket_name}"]
    condition {
      test     = "StringLike"
      variable = "s3:prefix"
      values   = ["${var.preview_state_key_prefix}/*"]
    }
  }
  statement {
    sid       = "ReadFoundationPreviewRole"
    actions   = ["iam:GetRole"]
    resources = [aws_iam_role.preview_lambda.arn]
  }
  statement {
    sid       = "PassFoundationPreviewRoleToLambda"
    actions   = ["iam:PassRole"]
    resources = [aws_iam_role.preview_lambda.arn]
    condition {
      test     = "StringEquals"
      variable = "iam:PassedToService"
      values   = ["lambda.amazonaws.com"]
    }
  }
  statement {
    sid = "ManagePreviewLambdaFunctions"
    actions = [
      "lambda:AddPermission", "lambda:CreateAlias", "lambda:CreateFunction",
      "lambda:DeleteAlias", "lambda:DeleteFunction", "lambda:GetAlias",
      "lambda:GetFunction", "lambda:GetFunctionCodeSigningConfig",
      "lambda:GetPolicy", "lambda:ListAliases", "lambda:ListVersionsByFunction",
      "lambda:PublishVersion", "lambda:RemovePermission", "lambda:TagResource",
      "lambda:UntagResource", "lambda:UpdateAlias", "lambda:UpdateFunctionCode",
      "lambda:UpdateFunctionConfiguration",
    ]
    resources = local.preview_lambda_arns
  }
  statement {
    sid = "ManagePreviewDynamoDbTables"
    actions = [
      "dynamodb:CreateTable", "dynamodb:DeleteTable",
      "dynamodb:DescribeContinuousBackups", "dynamodb:DescribeTable",
      "dynamodb:DescribeTimeToLive", "dynamodb:GetItem",
      "dynamodb:ListTagsOfResource", "dynamodb:Query",
      "dynamodb:TagResource", "dynamodb:UntagResource",
      "dynamodb:UpdateContinuousBackups", "dynamodb:UpdateTimeToLive",
    ]
    resources = local.preview_table_arns
  }
  statement {
    sid       = "ReadPreviewLogGroups"
    actions   = ["logs:DescribeLogGroups"]
    resources = ["*"]
  }
  statement {
    sid = "ManagePreviewLogGroups"
    actions = [
      "logs:CreateLogGroup", "logs:DeleteLogGroup", "logs:ListTagsForResource",
      "logs:PutRetentionPolicy", "logs:TagResource", "logs:UntagResource",
    ]
    resources = local.preview_log_arns
  }
  statement {
    sid       = "CreateTaggedPreviewApis"
    actions   = ["apigateway:POST"]
    resources = ["arn:${data.aws_partition.current.partition}:apigateway:${data.aws_region.current.name}::/apis"]
    condition {
      test     = "StringEquals"
      variable = "aws:RequestTag/Environment"
      values   = ["pr-preview"]
    }
  }
  statement {
    sid       = "ManageTaggedPreviewApis"
    actions   = ["apigateway:DELETE", "apigateway:GET", "apigateway:PATCH", "apigateway:POST", "apigateway:PUT"]
    resources = ["arn:${data.aws_partition.current.partition}:apigateway:${data.aws_region.current.name}::/apis/*"]
    condition {
      test     = "StringEquals"
      variable = "aws:ResourceTag/Environment"
      values   = ["pr-preview"]
    }
  }
  statement {
    sid       = "ReadPreviewRuntimeSecrets"
    actions   = ["secretsmanager:GetSecretValue", "ssm:GetParameter", "ssm:GetParameters"]
    resources = concat(local.preview_ssm_secret_arns, local.preview_secrets_manager_arns)
  }
  dynamic "statement" {
    for_each = length(var.preview_kms_key_arns) > 0 ? [1] : []
    content {
      sid       = "DecryptPreviewRuntimeSecrets"
      actions   = ["kms:Decrypt"]
      resources = var.preview_kms_key_arns
    }
  }
}

resource "aws_iam_role_policy" "preview_deploy" {
  name   = "${var.preview_role_name}-deploy"
  role   = aws_iam_role.preview.id
  policy = data.aws_iam_policy_document.preview_deploy.json
}
