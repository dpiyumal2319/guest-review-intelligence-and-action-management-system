from app.connectors.base import MockConnector
from app.connectors.booking_com import connector as booking_com
from app.connectors.google_business_profile import connector as google_business_profile
from app.connectors.tripadvisor import connector as tripadvisor


CONNECTORS: dict[str, MockConnector] = {
    connector.connector_key: connector
    for connector in (
        google_business_profile,
        booking_com,
        tripadvisor,
    )
}


def get_connector(connector_key: str) -> MockConnector:
    try:
        return CONNECTORS[connector_key]
    except KeyError as exc:
        known_connectors = ", ".join(sorted(CONNECTORS))
        raise ValueError(f"Unknown connector '{connector_key}'. Expected one of: {known_connectors}.") from exc
