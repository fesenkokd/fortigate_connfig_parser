import datetime
from pathlib import Path

import yaml
from rich import print as rprint

from parser_cls import FortiParser

file = "test_rule.txt"
# file = "fg-conf.txt"
current_directory = Path.cwd()
template_directory = Path(current_directory, "template")
result_directory = Path(current_directory, "result")


def count_prefixlen(mask):
    return sum(bin(int(x)).count("1") for x in mask.split("."))


class FileAction:

    def __init__(self, varname):
        self.varname = varname
        self.file_name = self._get_file_name(self.varname)

    def check_is_exist(self) -> bool:
        try:
            return self.file_name.is_file()
        except AttributeError:
            return False

    def read(self) -> dict:
        with open(self.file_name, "r") as _f:
            return yaml.safe_load(_f)

    def write(self, write_data) -> None:
        with open(self.file_name, "w") as _f:
            yaml.dump(write_data, _f)
            self.read()

    @staticmethod
    def save_result(data_list: list[str], name="result"):
        time_now = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M")
        file_name = f"commnads_for_result_by_{time_now}.txt"
        file_abs_name = Path(result_directory, file_name)
        with open(file_abs_name, "w") as _f:
            for line in data_list:
                _f.writelines(line)
        rprint(f"[green]Резутьтат записан в файл {file_name}")

    @staticmethod
    def _get_file_name(key: str) -> str:
        filename_dict = {
            "address": Path(current_directory, "address_accord.yml"),
            "service": Path(current_directory, "service_accord.yml"),
        }
        return filename_dict.get(key)


def _file_write(delta: dict | list, varname: str, vrf: str = None) -> None:
    global address_accordance
    global service_accordance
    if varname == "address":
        exist_data = address_accordance.read()
        exist_data |= delta
        address_accordance.write(exist_data)
    elif varname == "service":
        exist_data = service_accordance.read()
        exist_data |= delta
        service_accordance.write(exist_data)
    elif varname == "result":
        print(delta)
        time_now = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M")
        file_name = f"commands_for_{vrf}_at_{time_now}.txt"
        file_abs_name = Path(result_directory, file_name)
        with open(file_abs_name, "w") as _f:
            _f.write("".join(delta))
        rprint(f"[green]Результат записан в файл {file_name}")


address_accordance = FileAction("address")
service_accordance = FileAction("service")
result_file = FileAction


def create_objects(data: list[dict], object_type: str) -> list:
    object_storage = []
    object_storage_item = ""
    tcp_port, udp_port, service_group = [], [], []
    if object_type == "address":
        for object_item in data:
            object_type = object_item.get("object_type")
            if object_type == "prefix":
                if object_item.get("mask") == "255.255.255.255":
                    object_storage_item = create_host_objects(object_item)
                else:
                    object_storage_item = create_network_objects(object_item)
            elif object_type == "fqdn":
                object_storage_item = create_domain_object(object_item)
            elif object_type == "iprange":
                object_storage_item = create_iprange_object(object_item)
    elif object_type == "addrgrp":
        for object_item in data:
            object_storage_item = create_group_objects(object_item, "addrgrp")
    elif object_type == "services":
        for object_item in data:
            new_group = {}
            if "tcp_port" in object_item.keys() and "udp_port" in object_item.keys():
                # Надо создать сервис группу.
                tcp_port, tcp_name_list = create_service_objects(
                    object_item, "tcp_port"
                )
                udp_port, udp_name_list = create_service_objects(
                    object_item, "udp_port"
                )
                new_group["name"] = object_item.get("name")
                new_group["members"] = tcp_name_list + udp_name_list
                service_group = create_group_objects(new_group, "servgrp")

            elif "tcp_port" in object_item.keys():
                if len(object_item.get("tcp_port")) > 1:
                    # Надо создать сервис группу.
                    tcp_port, tcp_name_list = create_service_objects(
                        object_item, "tcp_port"
                    )
                    new_group["name"] = object_item.get("name")
                    new_group["members"] = tcp_name_list
                    service_group = create_group_objects(new_group, "servgrp")
                else:
                    tcp_port = create_service_objects(object_item, "tcp_port")
            elif "udp_port" in object_item.keys():
                if len(object_item.get("udp_port")) > 1:
                    # Надо создать сервис группу.
                    udp_port, udp_name_list = create_service_objects(
                        object_item, "udp_port"
                    )
                    new_group["name"] = object_item.get("name")
                    new_group["members"] = udp_name_list
                    service_group = create_group_objects(new_group, "servgrp")
                else:
                    udp_port = create_service_objects(object_item, "udp_port")
            for x in (tcp_port, udp_port, service_group):
                if x:
                    object_storage.append(x)
    elif object_type == "servgrp":
        for object_item in data:
            object_storage_item = create_group_objects(object_item, "servgrp")
    else:
        rprint(f"[red]Переданный тип объекта '{object_type}' - не найден!")
    if object_storage_item:
        object_storage.append(object_storage_item + "\n")
    return object_storage


def create_iprange_object(object_item: dict) -> str:
    """
    Создает IP range объект
    add address-range name "New Address Range 1" ip-address-first "192.0.2.1" ip-address-last "192.0.2.10"
    """
    global address_accordance
    new_data = {}
    name = object_item.get("name")
    start_ip = object_item.get("start_ip")
    end_ip = object_item.get("end_ip")
    new_name = f"iprange.{start_ip}-{end_ip}"
    if name not in address_accordance.read().keys():
        new_data[name] = new_name
        _file_write(new_data, "address")
    cp_range = f"add address-range name {new_name} ip-address-first {start_ip} ip-address-last {end_ip} comments '{name}' color 'crete blue'"
    # rprint(f"[green]{cp_range}")
    return cp_range


def create_domain_object(object_item: dict[str]) -> str:
    """
    Создает domain объект
    add dns-domain name ".www.example.com" is-sub-domain false
    """
    global address_accordance
    domain: str = object_item.get("fqdn")
    if not domain.startswith("."):
        domain = domain.lstrip("*.-/")
    name = object_item.get("name")
    cp_domain = f"add dns-domain name .{domain} is-sub-domain false color 'crete blue' comments '{name}'"
    # rprint(f"[green]{cp_domain}")
    return cp_domain


def create_network_objects(object_item: dict) -> str:
    global address_accordance
    new_data = {}
    prefix = object_item.get("prefix")
    mask = object_item.get("mask")
    if not mask:
        rprint(f"[yellow]{object_item}")
    name = object_item.get("name")
    prefixlen = count_prefixlen(mask)
    new_name = f"net.{prefix}/{prefixlen}"
    if name not in address_accordance.read().keys():
        new_data[name] = new_name
        _file_write(new_data, "address")
    cp_network = f"add network name {new_name} subnet {prefix} subnet-mask {mask} comments '{name}' color 'crete blue'"
    # rprint(f"[green]{cp_network}")
    return cp_network


def create_host_objects(object_item: dict) -> str:
    global address_accordance
    new_data = {}
    prefix = object_item.get("prefix")
    name = object_item.get("name")
    new_name = f"h.{prefix}"
    if name not in address_accordance.read().keys():
        new_data[name] = new_name
        _file_write(new_data, "address")
    cp_host = f"add host name {new_name} ip-address {prefix} comments '{name}' color 'crete blue'"
    # rprint(f"[green]{cp_host}")
    return cp_host


def create_group_objects(object_item: dict, group_type: str) -> str:
    """
    Добавление группы сетевых объектов
    add group name "New Group 4" members.1 "New Host 1" members.2 "My Test Host 3"
    """
    global address_accordance
    global service_accordance

    group_type_dict = {"addrgrp": address_accordance, "servgrp": service_accordance}
    group_syntax_dict = {"addrgrp": "group", "servgrp": "service-group"}
    accordance = group_type_dict.get(group_type)
    member_new_format_list = []
    new_name_member_list = []
    members_list = object_item.get("members")
    group_name = object_item.get("name")
    if not members_list:
        rprint(f"[red]{object_item}")
    for x in members_list:
        if x in accordance.read().keys():
            new_name_member_list.append(accordance.read().get(x))
        else:
            new_name_member_list.append(x)
    member_tuple = zip(range(1, 1 + len(new_name_member_list)), new_name_member_list)
    for x in member_tuple:
        member_str = f"members.{x[0]} {x[1]}"
        member_new_format_list.append(member_str)
    member_new_format_str = " ".join(member_new_format_list)
    cp_group = f"add {group_syntax_dict.get(group_type)} name {group_name} {member_new_format_str}"
    # rprint(f"[green]{cp_group}")
    return cp_group


def create_service_objects(object_item: dict, service_type: str) -> list[str]:
    """
    Добавление сервисов на CP
    add service-tcp name "New_TCP_Service_1" port 5669 comments '' color 'crete blue'
    add service-udp name "New_UDP_Service_1" port 5669
    """
    global service_accordance
    new_data = {}
    service_dict = {
        "tcp_port": "tcp",
        "udp_port": "udp",
    }
    try:
        protocol = service_dict.get(service_type)
    except KeyError:
        rprint(f"[yellow]Создание этого типа сервисы {service_type} не описано.")
    service_name_dict = {}
    service_list = []
    cp_commands_list = []
    if len(object_item.get(service_type)) > 1:
        newgroup_name = object_item.get("name")
        for serv in object_item.get(service_type):
            name = f"{service_type}_{serv}"
            if name not in service_accordance.read().keys():
                new_data[name] = name
                _file_write(new_data, "service")
            cp_service = f"add service-{protocol} name {name} port {serv}"
            # rprint(f"[green]{cp_service}")
            cp_commands_list.append(cp_service)
            service_list.append(name)
        service_name_dict[newgroup_name] = service_list
        return cp_commands_list, service_name_dict
    else:
        name_list = []
        serv = object_item.get(service_type)[0]
        name = f"{service_type}_{serv}"
        if name not in service_accordance.read().keys():
            new_data[name] = name
            _file_write(new_data, "service")
        cp_service = f"add service-{protocol} name {name} port {serv}"
        cp_commands_list.append(cp_service)
        # rprint(f"[blue]{cp_service}")
        name_list.append(name)
        return cp_commands_list, name_list


def object_create_serialization(data_for_vrf: dict) -> str:
    result = []
    all_object_type_list = ["address", "addrgrp", "services", "servgrp"]
    for object_type in all_object_type_list:
        data = data_for_vrf.get(object_type)
        result.append(create_objects(data, object_type))
    return result


def main(vrf_name=None, objects=None):
    setup_func()
    all_objects = []
    with open(file, "r", encoding="utf-8") as f:
        config = f.read()
    parsed_res = FortiParser(config)
    if vrf_name:
        data_for_vrf = parsed_res.vrf_rules(vrf_name)
        all_objects = object_create_serialization(data_for_vrf)
        _file_write(all_objects, "result", vrf_name)
    elif objects:
        if objects == "all":
            ...
        elif objects == "addresses":
            addresses = parsed_res.get_all_addresses()
            object_result = create_objects(addresses, object_type="address")
        elif objects == "services":
            ...
    else:
        print("Не выбрано ни одного аргумента.")


def setup_func():
    global address_accordance
    global service_accordance
    address_accordance = FileAction("address")
    service_accordance = FileAction("service")
    if not address_accordance.check_is_exist() or not address_accordance.read():
        addr_init_record = {"0_fortigate_name": "0_cp_name"}
        address_accordance.write(addr_init_record)  # Create file
    if not service_accordance.check_is_exist() or not service_accordance.read():
        service_init_record = {"HTTP": "http", "HTTPS": "https"}
        service_accordance.write(service_init_record)  # Create file
    address_accordance.read()
    service_accordance.read()


if __name__ == "__main__":
    main(vrf_name="VRF_DB")
    # main(vrf_name)
    # _file_write({"name3": "val3"}, "address")
    # file = "fg-conf.txt"
    # with open(file, "r", encoding="utf-8") as f:
    #    config = f.read()
    # parsed_res = FortiParser(config)
    # data = parsed_res.get_all_services()
    # create_objects(data, "services")
