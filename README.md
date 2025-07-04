# VM Management Service

A comprehensive virtual machine management service for the DESP-AAS platform. This service provides a unified API for managing virtual machines across OpenStack infrastructure, including lifecycle management, monitoring, and remote access capabilities.

## Overview

The VM Management Service is a microservice that acts as a gateway between the DESP-AAS platform and OpenStack infrastructure. It provides a RESTful API for creating, managing, and monitoring virtual machines, with integrated support for Apache Guacamole for remote access and Prometheus for metrics collection.

## Features

- **VM Lifecycle Management**: Create, start, stop, shelve, and delete servers
- **Remote Access**: Web-based SSH/RDP access via Apache Guacamole
- **Monitoring**: Real-time resource metrics via Prometheus
- **Automation**: Automatic suspension of inactive servers
- **Database Integration**: Persistent server state tracking

- **Server Creation**: Automated VM provisioning using Terraform and Ansible
- **Lifecycle Operations**: Start, stop, shelve, unshelve, reset, and delete servers
- **State Management**: Track server states throughout their lifecycle
- **Infrastructure Integration**: Seamless integration with OpenStack APIs

### 🔐 Remote Access

- **Apache Guacamole Integration**: Web-based remote access to VMs
- **Multi-protocol Support**: SSH and RDP connections
- **User Management**: Automatic user creation and group assignment
- **Connection Management**: Dynamic connection creation and cleanup

### 📊 Monitoring & Metrics

- **Prometheus Integration**: Real-time resource monitoring
- **Performance Metrics**: CPU, memory, disk, and network usage
- **Historical Data**: Time-series metrics with configurable time ranges
- **Resource Tracking**: Comprehensive server resource utilization

### 🔄 Lifecycle Automation

- **Automatic Suspension**: Suspend inactive servers to save resources
- **Notification System**: Email notifications for server lifecycle events
- **Cleanup Policies**: Automatic deletion of long-suspended servers
- **Background Processing**: Asynchronous lifecycle management

### 🗄️ Data Management

- **Database Integration**: Persistent server state tracking
- **Event Logging**: Comprehensive audit trail of server operations
- **Project Association**: Link servers to specific projects and users
- **Transaction Support**: ACID-compliant database operations

## Architecture

### Core Components

```
vm_management/
├── routes/v1/           # API endpoints
│   ├── servers.py       # Main server management endpoints
│   ├── openstack_servers.py  # OpenStack-specific operations
│   ├── guacemole.py     # Remote access configuration
│   └── metrics.py       # Monitoring and metrics endpoints
├── services/            # Business logic layer
│   ├── server_service.py      # Main server orchestration
│   ├── openstack_server_service.py  # OpenStack API integration
│   ├── guacamole_service.py   # Remote access management
│   ├── lifecycle_service.py   # Automated lifecycle management
│   ├── prometheus_service.py  # Metrics collection
│   ├── sandbox_db_service.py  # Database operations
│   └── infrastructure_service.py  # Terraform/Ansible integration
├── models/              # Data models and schemas
├── connectors/          # External service connectors
└── utils.py            # Utility functions
```

### Technology Stack

- **Framework**: FastAPI with MSFWK (Microservice Framework)
- **Infrastructure**: OpenStack SDK for cloud operations
- **Remote Access**: Apache Guacamole API integration
- **Monitoring**: Prometheus API client
- **Automation**: Ansible Runner for configuration management
- **Infrastructure as Code**: Terraform integration via Kubernetes jobs
- **Messaging**: RabbitMQ for asynchronous operations
- **Database**: PostgreSQL (via shared library)
- **Containerization**: Docker with multi-stage builds

## API Endpoints

### Server Management (`/servers`)

- `POST /` - Create a new server
- `GET /` - List all servers
- `GET /{server_id}` - Get server details
- `POST /{server_id}/actions/shelve` - Shelve a server
- `POST /{server_id}/actions/unshelve` - Unshelve a server
- `POST /{server_id}/actions/reset` - Reset a server
- `DELETE /{server_id}` - Delete a server
- `POST /{server_id}/actions/run-ansible` - Install applications
- `POST /suspended` - List suspended servers

### OpenStack Operations (`/openstack-servers`)

- `GET /` - List OpenStack servers
- `GET /{openstack_server_id}` - Get OpenStack server details
- `POST /{openstack_server_id}/actions/shelve` - Shelve OpenStack server
- `POST /{openstack_server_id}/actions/unshelve` - Unshelve OpenStack server
- `POST /{openstack_server_id}/actions/reset` - Reset OpenStack server
- `DELETE /{openstack_server_id}` - Delete OpenStack server

### Remote Access (`/guacamole`)

- `GET /base-url` - Get Guacamole base URL

### Monitoring (`/metrics`)

- `GET /resources/{server_id}/cpu` - Get CPU usage metrics
- `GET /resources/{server_id}/memory` - Get memory usage metrics
- `GET /resources/{server_id}/disk` - Get disk usage metrics
- `GET /resources/{server_id}/network` - Get network traffic metrics

## Configuration

The service uses environment variables and configuration files for setup:

### Key Configuration Options

- **OpenStack**: Connection parameters for OpenStack APIs
- **Guacamole**: Base URL, admin credentials, and connection settings
- **Prometheus**: Metrics collection endpoint and query parameters
- **Database**: Connection string and schema configuration
- **Lifecycle**: Suspension thresholds and notification settings

## Development

### Prerequisites

- Python 3.12+
- Docker and Docker Compose
- OpenStack access credentials
- PostgreSQL database
- RabbitMQ message broker

### Local Development Setup

```bash
# Clone the repository
git clone <repository-url>
cd vm_management

# Install dependencies
uv sync

# Set up environment variables
cp .env.example .env
# Edit .env with your configuration

# Run the service
uv run python -m vm_management.main
```

### Testing

```bash
# Run tests
pytest

# Run with coverage
pytest --cov=vm_management

# Run specific test categories
pytest tests/unit/
pytest tests/integration/
```

### Docker Build

```bash
# Build the Docker image
docker build -t vm-management .

# Run the container
docker run -p 8000:8000 vm-management
```

## Deployment

### Kubernetes Deployment

The service is designed to run in Kubernetes environments with:

- ConfigMaps for configuration management
- Secrets for sensitive data
- Service accounts for OpenStack authentication
- Horizontal Pod Autoscaler for scaling

### CI/CD Pipeline

- Automated testing on pull requests
- Docker image building and pushing
- Deployment to staging and production environments
- Integration with GitLab CI/CD

## Monitoring and Observability


### Logging

- Structured logging with correlation IDs
- Integration with centralized logging systems
- Audit trail for all server operations

### Metrics

- Prometheus metrics for service performance
- Custom metrics for business operations
- Integration with Grafana dashboards

## Security

### Authentication & Authorization

- Integration with DESP-AAS authentication system
- Role-based access control
- API key management for internal services

### Data Protection

- Encrypted communication with external services
- Secure credential management
- Audit logging for compliance

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests for new functionality
5. Ensure all tests pass
6. Submit a pull request

## License

This project is part of the DESP-AAS platform and follows the same licensing terms.

## Support

For support and questions:

- Create an issue in the GitLab repository
- Contact the DESP-AAS development team
- Check the project documentation

---

**Note**: This service is part of the larger DESP-AAS ecosystem and should be deployed alongside other microservices for full functionality.
