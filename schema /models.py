from __future__ import annotations

from ipaddress import ip_address, ip_network
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


ALLOWED_ROLES = {
    "compute-node", "tor-router", "spine-switch", "infrastructure-docs",
    "graph-database", "middleware", "storage-tor", "storage-controller",
    "object-storage", "metrics-collector", "metrics-exporter",
    "container-metrics", "metrics-dashboard",
}


class TopologyValidationError(ValueError):
    def __init__(self, errors: list[dict[str, Any]]):
        self.errors = errors
        super().__init__("Infrastructure topology validation failed")


class Interface(BaseModel):
    model_config = ConfigDict(extra="allow")
    name: str = Field(min_length=1)
    type: str | None = None
    role: str | None = None
    ip: str | None = None
    connects_to: str | None = None


class Container(BaseModel):
    model_config = ConfigDict(extra="allow")
    name: str = Field(min_length=1)
    image: str = Field(min_length=1)
    role: str
    ip: str | None = None
    port: int | None = Field(default=None, ge=1, le=65535)
    interfaces: list[Interface] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_container(self) -> "Container":
        if self.role not in ALLOWED_ROLES:
            raise ValueError(f"unsupported role '{self.role}'")
        names = [item.name for item in self.interfaces]
        if len(names) != len(set(names)):
            raise ValueError("interface names must be unique per device")
        if self.ip:
            ip_address(self.ip)
        for interface in self.interfaces:
            if interface.ip:
                ip_address(interface.ip)
        return self


class Site(BaseModel):
    name: str = Field(min_length=1)
    region: str = Field(min_length=1)


class VPC(BaseModel):
    name: str = Field(min_length=1)
    region: str = Field(min_length=1)
    cidr: str | None = None


class Subnet(BaseModel):
    name: str = Field(min_length=1)
    cidr: str
    description: str = ""

    @model_validator(mode="after")
    def validate_cidr(self) -> "Subnet":
        ip_network(self.cidr, strict=False)
        return self


class Network(BaseModel):
    vpc: VPC
    subnets: list[Subnet]


class Droplet(BaseModel):
    model_config = ConfigDict(extra="allow")
    name: str = Field(min_length=1)
    size: str
    image: str
    region: str
    subnet: str
    description: str = ""
    tags: list[str] = Field(default_factory=list)


class Link(BaseModel):
    model_config = ConfigDict(extra="allow")
    source: str
    target: str
    source_iface: str | None = None
    target_iface: str | None = None
    link_type: str = "network_link"
    description: str = ""


class Capacity(BaseModel):
    model_config = ConfigDict(extra="allow")
    id: str
    capacity: float = Field(ge=0)
    used: float = Field(default=0, ge=0)


RackCapacity = PowerCapacity = CoolingCapacity = StorageCapacity = Capacity


class InfrastructureSchema(BaseModel):
    model_config = ConfigDict(extra="allow")
    site: Site
    network: Network
    droplets: list[Droplet]
    containers: dict[str, list[Container]]
    links: list[Link]
    rack_capacities: list[RackCapacity] = Field(default_factory=list)
    power_capacities: list[PowerCapacity] = Field(default_factory=list)
    cooling_capacities: list[CoolingCapacity] = Field(default_factory=list)
    storage_capacities: list[StorageCapacity] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_references(self) -> "InfrastructureSchema":
        errors: list[dict[str, Any]] = []
        droplet_ids = [d.name for d in self.droplets]
        subnet_ids = [s.name for s in self.network.subnets]
        if len(droplet_ids) != len(set(droplet_ids)):
            errors.append(_error("DUPLICATE_DROPLET", "droplets", droplet_ids, "Droplet IDs must be unique"))
        if len(subnet_ids) != len(set(subnet_ids)):
            errors.append(_error("DUPLICATE_SUBNET", "network.subnets", subnet_ids, "Subnet IDs must be unique"))

        subnet_by_id = {s.name: ip_network(s.cidr, strict=False) for s in self.network.subnets}
        canonical: set[str] = set()
        local_to_ids: dict[str, list[str]] = {}
        interfaces: dict[str, set[str]] = {}
        for droplet, records in self.containers.items():
            if droplet not in droplet_ids:
                errors.append(_error("DROPLET_NOT_FOUND", f"containers.{droplet}", droplet, "Container group must reference an existing droplet"))
                continue
            droplet_model = next(d for d in self.droplets if d.name == droplet)
            if droplet_model.subnet not in subnet_by_id:
                errors.append(_error("SUBNET_NOT_FOUND", f"droplets.{droplet}.subnet", droplet_model.subnet, "Droplet subnet must exist"))
                continue
            for index, item in enumerate(records):
                node_id = f"{droplet}/{item.name}"
                if node_id in canonical:
                    errors.append(_error("DUPLICATE_NODE_ID", f"containers.{droplet}[{index}].name", node_id, "Canonical node ID must be unique"))
                canonical.add(node_id)
                local_to_ids.setdefault(item.name, []).append(node_id)
                interfaces[node_id] = {i.name for i in item.interfaces}
                if item.ip and ip_address(item.ip) not in subnet_by_id[droplet_model.subnet]:
                    errors.append(_error("IP_OUTSIDE_SUBNET", f"containers.{droplet}[{index}].ip", item.ip, f"IP must belong to {droplet_model.subnet}"))

        def resolve(value: str) -> str | None:
            if value in canonical:
                return value
            matches = local_to_ids.get(value, [])
            return matches[0] if len(matches) == 1 else None

        for index, link in enumerate(self.links):
            source = resolve(link.source)
            target = resolve(link.target)
            if not source:
                errors.append(_error("LINK_ENDPOINT_NOT_FOUND", f"links[{index}].source", link.source, "Link source must resolve to one canonical node"))
            if not target:
                errors.append(_error("LINK_ENDPOINT_NOT_FOUND", f"links[{index}].target", link.target, "Link target must resolve to one canonical node"))
            if source and link.source_iface and link.source_iface not in interfaces[source]:
                errors.append(_error("INTERFACE_NOT_FOUND", f"links[{index}].source_iface", link.source_iface, "Source interface must exist"))
            if target and link.target_iface and link.target_iface not in interfaces[target]:
                errors.append(_error("INTERFACE_NOT_FOUND", f"links[{index}].target_iface", link.target_iface, "Target interface must exist"))

        # Shelf/expander references model external storage hardware not represented as containers.
        for droplet, records in self.containers.items():
            for index, item in enumerate(records):
                for iface_index, iface in enumerate(item.interfaces):
                    if not iface.connects_to:
                        continue
                    base = iface.connects_to.split(":", 1)[0]
                    if resolve(base) is None and not base.startswith("shelf-"):
                        errors.append(_error(
                            "CONNECTS_TO_NOT_FOUND",
                            f"containers.{droplet}[{index}].interfaces[{iface_index}].connects_to",
                            iface.connects_to,
                            "Interface target must resolve to an existing node or declared external shelf",
                        ))
        if errors:
            raise TopologyValidationError(errors)
        return self


def _error(code: str, path: str, value: Any, message: str) -> dict[str, Any]:
    safe_value = str(value)
    return {"code": code, "path": path, "value": safe_value[:200], "message": message}
