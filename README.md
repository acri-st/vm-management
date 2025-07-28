# VM Management

📌 [DESP-AAS Sandbox Parent Repository](https://github.com/acri-st/DESP-AAS-Sandbox)

## Table of Contents

- [Introduction](#Introduction)
- [Prerequisites](#prerequisites)
- [Installation](#installation)
- [Development](#development)
- [Testing](#testing)
- [Contributing](#contributing)
- [Deployment](#deployment)
- [License](#license)
- [Support](#support)

## Introduction

###  What is the Sandbox?

Sandbox is a service that allows users to develop applications and models using cloud based services and to ease the deployment .

The Microservices that make up the Sandbox project are the following: 
- **Auth** Authentication service tu authenticate users.
- **Project management** Project management system.
- **VM management** manages the virtual machines for the projects. These virtual machines are where the user manages their project and develops.
- **Storage** Manages the project git files.


### What is the VM Management?

The VM Management service is a microservice that manages virtual machines for projects. It provides the infrastructure and tools necessary for users to create, configure, and manage virtual machines where they develop and run their applications and models.

The VM Management service handles:
- **VM Provisioning** Creating and deploying virtual machines for user projects
- **Resource Management** Allocating and monitoring compute resources (CPU, memory, storage)
- **Lifecycle Management** Starting, stopping, and terminating VMs as needed
- **Configuration Management** Setting up development environments and required software
- **Integration** Working with other microservices like Project Management and Storage

This service is a critical component of the Sandbox, providing the development environment where users can build and test their applications before deploying to the main collaborative platform.

## Prerequisites

Before you begin, ensure you have the following installed:
- **Git** 
- **Docker** Docker is mainly used for the test suite, but can also be used to deploy the project via docker compose

## Installation

1. Clone the repository:
```bash
git clone https://github.com/acri-st/vm-management.git
cd vm-management
```

## Development

## Development Mode

### Standard local development

Setup environment
```bash
make setup
```

Start the development server:
```bash
make start
```

To clean the project and remove node_modules and other generated files, use:
```bash
make clean
```

## Contributing

Check out the **CONTRIBUTING.md** for more details on how to contribute.
