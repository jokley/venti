#!/bin/bash

set -e

echo "Updating system packages..."
sudo apt update
sudo apt upgrade -y

echo "Installing prerequisites..."
sudo apt install -y ca-certificates curl gnupg lsb-release

echo "Adding Docker’s official GPG key..."
sudo mkdir -p /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/debian/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg

echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/debian \
  $(lsb_release -cs) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

echo "Updating package list again..."
sudo apt update

echo "Installing Docker Engine and Docker Compose plugin..."
sudo apt install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin

echo "Adding user '$USER' to docker group..."
sudo usermod -aG docker $USER

echo "Enabling and starting Docker service..."
sudo systemctl enable docker
sudo systemctl start docker

echo "Docker and Docker Compose installation complete!"
echo "Please logout and login again (or reboot) to apply user group changes."
