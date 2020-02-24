import os
import socket
import struct

if os.name == "nt":
    import win32api as fcntl
else:
    import fcntl  # type: ignore


def get_ip_address(ifname):
    """
    Returns the IPv4 address of the requested interface (thanks Martin Konecny, https://stackoverflow.com/a/24196955)

    :param string interface: The interface to get the IPv4 address of.

    :returns: The interface's IPv4 address.

    """
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    return socket.inet_ntoa(
        fcntl.ioctl(s.fileno(), 0x8915, struct.pack("256s", bytes(ifname[:15], "utf-8")))[20:24]
    )  # SIOCGIFADDR


def send_discovery_packet(timeout=2, interface=False, ip_address=None):
    if ip_address is None:
        ip_address = "239.255.255.250"

    msg = "\r\n".join(["M-SEARCH * HTTP/1.1", "HOST: " + ip_address + ":1982", 'MAN: "ssdp:discover"', "ST: wifi_bulb"])

    # Set up UDP socket
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    s.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 32)
    if interface:
        s.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_IF, socket.inet_aton(get_ip_address(interface)))
    s.settimeout(timeout)
    s.sendto(msg.encode(), (ip_address, 1982))

    return s


def parse_capabilities(data):
    return dict([x.strip("\r").split(": ") for x in data.decode().split("\n") if ":" in x])


def filter_lower_case_keys(dict):
    return {key: value for key, value in dict.items() if key.islower()}
