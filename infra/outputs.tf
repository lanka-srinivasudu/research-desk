output "public_ip" {
  description = "Public IP of the research-desk VM"
  value       = oci_core_instance.research_desk.public_ip
}

output "ssh_command" {
  description = "Command to connect to the VM"
  value       = "ssh ubuntu@${oci_core_instance.research_desk.public_ip}"
}

output "board_url" {
  description = "Public board URL once the app is serving on port 80"
  value       = "http://${oci_core_instance.research_desk.public_ip}/"
}
