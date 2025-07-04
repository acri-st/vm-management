"""Service for querying Prometheus metrics"""

import json
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
from pydantic import BaseModel

from msfwk.utils.config import read_config
from msfwk.utils.logging import get_logger
from vm_management.exceptions import PrometheusError

logger = get_logger("application")


class PrometheusConfig(BaseModel):
    """Configuration for Prometheus service"""

    url: str
    job_name: str
    environment: str
    mountpoints: list[str]


class PrometheusService:
    """Service for querying Prometheus metrics"""

    def __init__(self, config: PrometheusConfig) -> None:
        """Initialize Prometheus service

        Args:
            config: Prometheus configuration
        """
        self.config = config
        self.url = config.url
        # Don't verify SSL certs for Prometheus
        self.client = httpx.AsyncClient(verify=False, timeout=30.0)

    def _calculate_step(self, start_time: datetime, end_time: datetime) -> int:
        """Calculate step size using a single linear function based on the time range

        Args:
            start_time: Query start time
            end_time: Query end time

        Returns:
            Step size in seconds
        """
        # Calculate time difference in seconds
        time_diff = (end_time - start_time).total_seconds()

        # Define time range boundaries for the linear function
        min_time = 3600  # 1 hour
        max_time = 28 * 24 * 3600  # 4 weeks

        # Define step size boundaries
        min_step = 300  # 5 minutes for 1 hour
        max_step = 9676  # ~161 minutes for 4 weeks

        if time_diff <= min_time:
            # For very short ranges, use minimum step
            step_seconds = min_step
        else:
            # Single linear function from MIN_TIME to MAX_TIME
            ratio = (time_diff - min_time) / (max_time - min_time)
            step_seconds = min_step + ratio * (max_step - min_step)

        return int(round(step_seconds))

    async def _query_range(
        self, query: str, start_time: datetime, end_time: datetime, step: str = None
    ) -> list[dict[str, Any]]:
        """Execute a Prometheus query_range request

        Args:
            query: PromQL query string
            start_time: Start time for the query
            end_time: End time for the query
            step: Query resolution step width (optional, calculated if not provided)

        Returns:
            List of query results

        Raises:
            PrometheusError: If the Prometheus API call fails
        """
        # Calculate step if not provided
        if step is None:
            step = self._calculate_step(start_time, end_time)
            logger.debug(
                "Calculated step size: %s for time range %s to %s", step, start_time.isoformat(), end_time.isoformat()
            )

        params = {"query": query, "start": start_time.timestamp(), "end": end_time.timestamp(), "step": step}

        try:
            url = f"{self.url}/api/v1/query_range"
            logger.debug("Executing Prometheus query: %s", url)

            response = await self.client.get(url, params=params)
            response.raise_for_status()

            result = response.json()

            if result.get("status") != "success":
                error_msg = result.get("error", "Unknown error")
                logger.error("Prometheus API returned error: %s", error_msg)
                raise PrometheusError(f"Prometheus query failed: {error_msg}")

            return result.get("data", {}).get("result", [])

        except httpx.RequestError as exc:
            logger.error("Error making request to Prometheus: %s", str(exc))
            raise PrometheusError(f"Failed to connect to Prometheus: {exc!s}")
        except httpx.HTTPStatusError as exc:
            logger.error("HTTP error from Prometheus API: %s", str(exc))
            raise PrometheusError(f"Prometheus API returned error: {exc!s}")
        except json.JSONDecodeError as exc:
            logger.error("Failed to parse Prometheus response: %s", str(exc))
            raise PrometheusError(f"Failed to parse Prometheus response: {exc!s}")
        except Exception as exc:
            logger.error("Unexpected error querying Prometheus: %s", str(exc))
            raise PrometheusError(f"Unexpected error querying Prometheus: {exc!s}")

    async def get_cpu_usage(self, openstack_server_id: str, time_range: int = 3600) -> dict[str, Any]:
        """Get CPU usage for a specific server

        Args:
            openstack_server_id: The ID of the server instance
            time_range: Time range in seconds to query (default: 1 hour)

        Returns:
            Dict containing CPU usage data

        Raises:
            PrometheusError: If there's an error querying Prometheus
            ResourceNotFoundError: If no metrics found for the server
        """
        logger.info("Getting CPU usage for server_id=%s", openstack_server_id)

        end_time = datetime.now(timezone.utc)
        start_time = end_time - timedelta(seconds=time_range)

        # Using string formatting to make the query more readable
        query = f"""
            100 - (
                avg by (instance) (
                    rate(
                        node_cpu_seconds_total{{
                            mode="idle", 
                            instance_id="{openstack_server_id}", 
                            environment="{self.config.environment}", 
                            job="{self.config.job_name}"
                        }}[5m]
                    )
                )
            ) * 100
        """

        # Remove extra whitespace for the actual query
        query = " ".join(line.strip() for line in query.strip().splitlines())

        logger.debug("CPU query: %s", query)

        # Don't specify step to use calculated step size
        result = await self._query_range(query=query, start_time=start_time, end_time=end_time)

        if not result:
            logger.warning("No CPU metrics found for server_id=%s", openstack_server_id)

        return self._format_metric_result(result, "CPU Usage (%)")

    async def get_memory_usage(self, openstack_server_id: str, time_range: int = 3600) -> dict[str, Any]:
        """Get memory usage for a specific server

        Args:
            openstack_server_id: The ID of the server instance
            time_range: Time range in seconds to query (default: 1 hour)

        Returns:
            Dict containing memory usage data

        Raises:
            PrometheusError: If there's an error querying Prometheus
            ResourceNotFoundError: If no metrics found for the server
        """
        logger.info("Getting memory usage for server_id=%s", openstack_server_id)

        end_time = datetime.now(timezone.utc)
        start_time = end_time - timedelta(seconds=time_range)

        # Memory used percentage
        query = f"""
            (
                1 - (
                    node_memory_MemAvailable_bytes{{
                        instance_id="{openstack_server_id}",
                        environment="{self.config.environment}",
                        job="{self.config.job_name}"
                    }} / 
                    node_memory_MemTotal_bytes{{
                        instance_id="{openstack_server_id}",
                        environment="{self.config.environment}",
                        job="{self.config.job_name}"
                    }}
                )
            ) * 100
        """

        # Remove extra whitespace for the actual query
        query = " ".join(line.strip() for line in query.strip().splitlines())

        logger.debug("Memory query: %s", query)

        # Don't specify step to use calculated step size
        result = await self._query_range(query=query, start_time=start_time, end_time=end_time)

        if not result:
            logger.warning("No memory metrics found for server_id=%s", openstack_server_id)

        return self._format_metric_result(result, "Memory Usage (%)")

    async def get_disk_usage(self, openstack_server_id: str, time_range: int = 3600) -> dict[str, Any]:
        """Get disk usage for a specific server

        Args:
            openstack_server_id: The ID of the server instance
            time_range: Time range in seconds to query (default: 1 hour)

        Returns:
            Dict containing disk usage data

        Raises:
            PrometheusError: If there's an error querying Prometheus
            ResourceNotFoundError: If no metrics found for the server
        """
        end_time = datetime.now(timezone.utc)
        start_time = end_time - timedelta(seconds=time_range)

        results = {}
        for mountpoint in self.config.mountpoints:
            logger.info("Getting disk usage for server_id=%s, mountpoint=%s", openstack_server_id, mountpoint)
            # Disk used percentage
            query = f"""
                100 - (
                    (
                        node_filesystem_avail_bytes{{
                            instance_id="{openstack_server_id}",
                            environment="{self.config.environment}",
                            job="{self.config.job_name}",
                            mountpoint="{mountpoint}"
                        }} / 
                        node_filesystem_size_bytes{{
                            instance_id="{openstack_server_id}",
                            environment="{self.config.environment}",
                            job="{self.config.job_name}",
                            mountpoint="{mountpoint}"
                        }}
                    ) * 100
                )
            """

            # Remove extra whitespace for the actual query
            query = " ".join(line.strip() for line in query.strip().splitlines())

            logger.debug("Disk query: %s", query)

            # Don't specify step to use calculated step size
            result = await self._query_range(query=query, start_time=start_time, end_time=end_time)

            if not result:
                logger.warning("No disk metrics found for server_id=%s, mountpoint=%s", openstack_server_id, mountpoint)

            results[mountpoint] = self._format_metric_result(result, f"Disk Usage ({mountpoint}) (%)")

        return results

    async def get_network_traffic(self, openstack_server_id: str, time_range: int = 3600) -> dict[str, Any]:
        """Get network traffic for a specific server

        Args:
            openstack_server_id: The ID of the server instance
            time_range: Time range in seconds to query (default: 1 hour)

        Returns:
            Dict containing network traffic data

        Raises:
            PrometheusError: If there's an error querying Prometheus
            ResourceNotFoundError: If no metrics found for the server
        """
        logger.info("Getting network traffic for server_id=%s", openstack_server_id)

        end_time = datetime.now(timezone.utc)
        start_time = end_time - timedelta(seconds=time_range)

        # Network receive bytes
        rx_query = f"""
            rate(
                node_network_receive_bytes_total{{
                    instance_id="{openstack_server_id}",
                    environment="{self.config.environment}",
                    job="{self.config.job_name}"
                }}[5m]
            )
        """

        # Network transmit bytes
        tx_query = f"""
            rate(
                node_network_transmit_bytes_total{{
                    instance_id="{openstack_server_id}",
                    environment="{self.config.environment}",
                    job="{self.config.job_name}"
                }}[5m]
            )
        """

        # Remove extra whitespace for the actual queries
        rx_query = " ".join(line.strip() for line in rx_query.strip().splitlines())
        tx_query = " ".join(line.strip() for line in tx_query.strip().splitlines())

        logger.debug("Network RX query: %s", rx_query)
        logger.debug("Network TX query: %s", tx_query)

        # Don't specify step to use calculated step size
        rx_result = await self._query_range(query=rx_query, start_time=start_time, end_time=end_time)
        tx_result = await self._query_range(query=tx_query, start_time=start_time, end_time=end_time)

        if not rx_result and not tx_result:
            logger.warning("No network metrics found for server_id=%s", openstack_server_id)

        return {
            "receive": self._format_metric_result(rx_result, "Network Receive (bytes/s)"),
            "transmit": self._format_metric_result(tx_result, "Network Transmit (bytes/s)"),
        }

    async def get_server_resources(self, openstack_server_id: str, time_range: int = 3600) -> dict[str, Any]:
        """Get all resource metrics for a specific server

        Args:
            openstack_server_id: The ID of the server instance
            time_range: Time range in seconds to query (default: 1 hour)

        Returns:
            Dict containing all resource metrics

        Raises:
            PrometheusError: If there's an error querying Prometheus
        """
        logger.info("Getting all resource metrics for server_id=%s", openstack_server_id)

        try:
            cpu_data = await self.get_cpu_usage(openstack_server_id, time_range)
            memory_data = await self.get_memory_usage(openstack_server_id, time_range)
            disk_data = await self.get_disk_usage(openstack_server_id, time_range)
            network_data = await self.get_network_traffic(openstack_server_id, time_range)

            return {
                "cpu": cpu_data,
                "memory": memory_data,
                "disk": disk_data,
                "network": network_data,
            }
        except Exception as e:
            logger.error("Error getting server resources: %s", str(e))
            raise PrometheusError(f"Failed to retrieve server resources: {e!s}")

    async def close(self):
        """Close the HTTP client session"""
        await self.client.aclose()

    def _format_metric_result(self, result: list[dict[str, Any]], metric_name: str) -> dict[str, Any]:
        """Format the metric result from Prometheus

        Args:
            result: Raw result from Prometheus query
            metric_name: Name of the metric

        Returns:
            Formatted metric data
        """
        if not result:
            return {"name": metric_name, "data": []}

        data = []
        for item in result:
            if "values" in item:
                # Extract timestamps and values
                timestamps = [value[0] for value in item["values"]]
                values = [float(value[1]) for value in item["values"]]

                data.extend([{"timestamp": ts, "value": val} for ts, val in zip(timestamps, values, strict=False)])

        return {"name": metric_name, "data": sorted(data, key=lambda x: x["timestamp"])}


async def get_prometheus_config() -> PrometheusConfig:
    """Get Prometheus configuration"""
    environment = read_config().get("general").get("application_environment")
    config = read_config().get("metrics")
    url = config.get("server")
    mountpoints = ["/", "/mount/data"]
    return PrometheusConfig(url=url, job_name="vm-ovh-instances", environment=environment, mountpoints=mountpoints)


async def get_prometheus_service() -> PrometheusService:
    """Get instance of PrometheusService

    Returns
        PrometheusService instance
    """
    config = await get_prometheus_config()
    return PrometheusService(config)
