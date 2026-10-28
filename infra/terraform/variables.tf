# Input variables for the StudySpot AWS deployment.
#
# Every default is chosen to keep a demo deployment cheap. The comments say what
# each one costs when you raise it, because the difference between this stack at
# ~$15/month and the same stack at ~$80/month is four of these values.

variable "project" {
  description = "Name prefix for every resource."
  type        = string
  default     = "studyspot"

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{1,20}$", var.project))
    error_message = "The project name must be lowercase alphanumeric with hyphens, 2-21 characters."
  }
}

variable "environment" {
  description = <<-EOT
    Deployment environment. Used in resource names, so one account can hold
    several.

    It is not a branch name and does not track one: the repository integrates
    on develop and releases on main, while this names a stack.

    Changing it on a stack that already exists replaces that stack. It feeds
    name_prefix, which names the database, the site bucket, both Lambda
    functions, their log groups and the database secret, and Terraform renames
    none of those in place -- it destroys and recreates them, taking the
    database and everything uploaded to the bucket with them. Create a second
    stack with a different value; do not rename a live one.
  EOT
  type        = string
  default     = "staging"

  validation {
    condition     = contains(["staging", "production"], var.environment)
    error_message = "The environment must be either staging or production."
  }
}

variable "region" {
  description = <<-EOT
    AWS region for everything except the CloudFront certificate.

    us-east-2 rather than the more usual us-east-1 because the organization this
    account belongs to applies a region-scoped service control policy: EC2, RDS,
    Lambda and Secrets Manager are permitted in us-east-2 and explicitly denied
    elsewhere. An apply against another region fails at the first call with an
    UnauthorizedOperation naming the policy, not with anything that looks like a
    configuration error.

    One consequence worth knowing: CloudFront requires ACM certificates in
    us-east-1, which that policy denies. A custom domain is therefore blocked
    until the policy changes. The default CloudFront certificate needs no ACM,
    so nothing here is affected today.
  EOT
  type        = string
  default     = "us-east-2"
}

# -- Network -------------------------------------------------------------------

variable "vpc_cidr" {
  description = "CIDR block for the VPC."
  type        = string
  default     = "10.20.0.0/16"
}

variable "az_count" {
  description = <<-EOT
    Availability zones to spread subnets across. RDS requires a subnet group with
    at least two, so two is the minimum even for a single-AZ instance.
  EOT
  type        = number
  default     = 2

  validation {
    condition     = var.az_count >= 2 && var.az_count <= 3
    error_message = "Between two and three availability zones are supported."
  }
}

# -- Database ------------------------------------------------------------------

variable "db_instance_class" {
  description = <<-EOT
    RDS instance class. db.t4g.micro is Graviton, the cheapest class that runs
    Postgres, and is covered by the 12-month AWS free tier. db.t4g.small roughly
    doubles the bill.
  EOT
  type        = string
  default     = "db.t4g.micro"
}

variable "db_engine_version" {
  description = "Postgres major version. Minor upgrades are applied automatically."
  type        = string
  default     = "17"
}

variable "db_allocated_storage" {
  description = "Storage in GB. 20 is the gp3 minimum and the free-tier allowance."
  type        = number
  default     = 20
}

variable "db_name" {
  description = "Initial database name."
  type        = string
  default     = "studyspot"
}

variable "db_username" {
  description = "Master username. The password is generated and never committed."
  type        = string
  default     = "studyspot"
}

variable "db_multi_az" {
  description = "Run a standby in a second AZ. Roughly doubles the database cost."
  type        = bool
  default     = false
}

variable "db_backup_retention_days" {
  description = <<-EOT
    Automated backup retention. Zero disables backups entirely.

    One day, not the seven a production database would want, because an account
    on the AWS Free Plan is capped: CreateDBInstance fails outright with
    FreeTierRestrictionError rather than silently clamping the value. Raise it
    after the account moves to a paid plan, and raise it before this database
    holds anything that cannot be rebuilt from data/spots.json -- favourites and
    reviews, when the backlog reaches them, are exactly that.
  EOT
  type        = number
  default     = 1
}

variable "database_publicly_accessible" {
  description = <<-EOT
    Whether the database gets a public endpoint.

    false (default) places RDS in private subnets. Only the Lambda functions in
    this VPC can reach it. This is the safe setting, and it is why migrations and
    data loads run as Lambda invocations rather than from a laptop.

    true places RDS in public subnets with a public address, still TLS-only and
    still restricted to database_allowed_cidrs. Set this only if something
    outside the VPC genuinely has to reach the database. The tradeoff is an
    endpoint reachable from the internet by anyone inside those CIDRs, so pair
    it with a narrow allowlist.
  EOT
  type        = bool
  default     = false
}

variable "database_allowed_cidrs" {
  description = <<-EOT
    CIDR blocks allowed to reach Postgres when database_publicly_accessible is
    true. Name the narrowest ranges that work: an allowlist of 0.0.0.0/0 is a
    database on the public internet behind one password.
  EOT
  type        = list(string)
  default     = []

  validation {
    condition     = alltrue([for cidr in var.database_allowed_cidrs : can(cidrhost(cidr, 0))])
    error_message = "Every entry must be a valid CIDR block."
  }
}

variable "db_deletion_protection" {
  description = "Refuse to destroy the database. Leave this on for production."
  type        = bool
  default     = false
}

variable "db_skip_final_snapshot" {
  description = "Skip the final snapshot on destroy. Convenient for a demo, wrong for production."
  type        = bool
  default     = true
}

# -- Lambda --------------------------------------------------------------------

variable "lambda_package_path" {
  description = <<-EOT
    Path to the deployment zip, relative to this directory. Build it first with
    infra/scripts/build-lambda.sh, which cross-compiles the backend's
    dependencies for the arm64 Lambda runtime.
  EOT
  type        = string
  default     = "../build/studyspot-api.zip"
}

variable "api_memory_mb" {
  description = <<-EOT
    Memory for the API function. Lambda scales CPU with memory, so raising this
    often lowers cost per request by shortening the duration billed.
  EOT
  type        = number
  default     = 512
}

variable "api_timeout_seconds" {
  description = "Request timeout for the API function."
  type        = number
  default     = 15
}

variable "manage_memory_mb" {
  description = <<-EOT
    Memory for the management function. load_spots holds the whole snapshot in
    memory and validates every record before writing.
  EOT
  type        = number
  default     = 1024
}

variable "manage_timeout_seconds" {
  description = "Timeout for management commands. Migrations are the slow case."
  type        = number
  default     = 300
}

variable "lambda_role_arn" {
  description = <<-EOT
    An existing execution role for both functions. Leave empty to have Terraform
    create one, which is what a normal account should do.

    Set it when the account forbids iam:CreateRole and hands you a preset role
    instead, as course lab environments do. The role must allow the Lambda
    service to assume it and must carry AWSLambdaVPCAccessExecutionRole or
    equivalent, or the functions cannot create their network interfaces.
  EOT
  type        = string
  default     = ""
}

# -- Django --------------------------------------------------------------------

variable "django_allowed_hosts" {
  description = <<-EOT
    Value for DJANGO_ALLOWED_HOSTS. The default is permissive because CloudFront
    does not forward the Host header to a Lambda function URL, so the host Django
    sees is the function URL's own rather than anything a viewer controls, and the
    URL already refuses requests that CloudFront has not signed.
  EOT
  type        = string
  default     = "*"
}

variable "django_csrf_trusted_origins" {
  description = <<-EOT
    Origins allowed to submit session-authenticated writes, as full origins such
    as https://d111111abcdef8.cloudfront.net.

    Needed only once the admin or another session-authenticated write exists. It
    is a variable rather than a reference to the distribution because the
    distribution depends on the function URL, and reading its domain from the
    function's environment would be a dependency cycle: apply once, then add the
    printed domain here.
  EOT
  type        = list(string)
  default     = []
}

variable "django_enable_admin" {
  description = <<-EOT
    Mount the Django admin. Off by default: it is reachable from the internet
    through CloudFront, and until the backlog reaches accounts there is nothing
    guarding it but a superuser password nobody has created.
  EOT
  type        = bool
  default     = false
}

# -- Accounts ------------------------------------------------------------------

variable "auth0_domain" {
  description = <<-EOT
    The Auth0 tenant's domain, such as studyspot.us.auth0.com. Blank leaves
    accounts switched off, and the site hides its log-in controls.
  EOT
  type        = string
  default     = ""
}

variable "auth0_client_id" {
  description = <<-EOT
    Client ID of the Auth0 single-page application. Public by design: every
    browser that logs in reads it.
  EOT
  type        = string
  default     = ""
}

variable "auth0_audience" {
  description = "Identifier of the Auth0 API that access tokens are issued for."
  type        = string
  default     = ""
}

variable "auth0_jwks" {
  description = <<-EOT
    The tenant's public signing keys: the JSON served at
    https://<auth0_domain>/.well-known/jwks.json, verbatim.

    The API function runs in private subnets with no NAT gateway (see
    network.tf), so it cannot fetch these itself. They are public keys, not a
    secret. Auth0 changes them only when someone rotates the signing key in the
    dashboard; re-apply with the new document when that happens, or every log-in
    is refused.
  EOT
  type        = string
  default     = ""

  validation {
    condition     = var.auth0_jwks == "" || can(jsondecode(var.auth0_jwks).keys)
    error_message = "auth0_jwks must be the JSON document from /.well-known/jwks.json."
  }
}

variable "api_reserved_concurrency" {
  description = <<-EOT
    Concurrent executions reserved for the API function.

    This is a blast-radius control rather than a performance setting. Lambda and
    API Gateway are billed per request and nothing in front of them rate-limits:
    neither CloudFront nor the gateway does by default, so a script pointed at
    the public endpoint spends the account's credits as fast as it can issue
    requests. A reservation caps how fast that can happen, and caps it whether
    the traffic arrives through CloudFront or directly.

    Ten is far above what a demo needs -- a request takes about 200 ms -- and far
    below what would empty the credit balance unnoticed. Raise it if real traffic
    ever queues; a 429 under load is the symptom.

    AWS requires at least 100 of the account's concurrency to stay unreserved.
    This account allows 400, so the reservations here leave 389.
  EOT
  type        = number
  default     = 10
}

variable "manage_reserved_concurrency" {
  description = <<-EOT
    Concurrent executions reserved for the management function.

    One, so that two invocations cannot run at once. This function applies
    migrations and replaces the contents of the spots table; two concurrent
    load_spots runs would interleave a delete with an insert, and two concurrent
    migrates would race on the same migration. Serialising it is the point.
  EOT
  type        = number
  default     = 1
}

variable "log_retention_days" {
  description = "CloudWatch log retention. Logs kept forever are a slow, quiet cost."
  type        = number
  default     = 14
}

# -- Frontend ------------------------------------------------------------------

variable "cloudfront_price_class" {
  description = <<-EOT
    PriceClass_100 covers North America and Europe and is the cheapest. StudySpot
    is a New York City dataset, so the default is deliberate rather than lazy.
  EOT
  type        = string
  default     = "PriceClass_100"

  validation {
    condition     = contains(["PriceClass_100", "PriceClass_200", "PriceClass_All"], var.cloudfront_price_class)
    error_message = "Must be PriceClass_100, PriceClass_200, or PriceClass_All."
  }
}

variable "site_bucket_force_destroy" {
  description = "Allow destroying the site bucket while it still holds objects."
  type        = bool
  default     = true
}
