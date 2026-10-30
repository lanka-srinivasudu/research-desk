# OCI account credentials. Supply these via terraform.tfvars (git-ignored)
# or environment variables (TF_VAR_tenancy_ocid, etc). Never commit them.

variable "tenancy_ocid" {
  description = "OCID of the tenancy"
  type        = string
}

variable "user_ocid" {
  description = "OCID of the user calling the API"
  type        = string
}

variable "fingerprint" {
  description = "Fingerprint of the API signing key"
  type        = string
}

variable "private_key_path" {
  description = "Local path to the API signing private key"
  type        = string
}

variable "compartment_ocid" {
  description = "OCID of the compartment to create resources in"
  type        = string
}

variable "region" {
  description = "Home region, e.g. ap-hyderabad-1"
  type        = string
}

variable "ssh_public_key_path" {
  description = "Local path to the SSH public key for the opc/ubuntu user"
  type        = string
  default     = "~/.ssh/id_rsa.pub"
}

# Always Free Arm allowance was cut from 4 OCPU / 24 GB to 2 OCPU / 12 GB
# in mid-2026. Staying within 2/12 keeps this free.
variable "ocpus" {
  description = "OCPUs for the A1.Flex shape (max 2 on Always Free)"
  type        = number
  default     = 2
}

variable "memory_in_gbs" {
  description = "Memory in GB for the A1.Flex shape (max 12 on Always Free)"
  type        = number
  default     = 12
}

# If Oracle returns "Out of host capacity", try a different index here
# rather than pinning a fault domain.
variable "availability_domain_index" {
  description = "Index into the tenancy's availability domains"
  type        = number
  default     = 0
}
