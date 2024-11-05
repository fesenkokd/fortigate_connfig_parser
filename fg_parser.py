from pathlib import Path

from rich import print as rprint
from ttp import ttp

current_directory = Path.cwd()
template_directory = Path(current_directory, "template")


class FortiParser:
    def __init__(self, config):
        self.config = config
        self.parsed_rules = self._parse_rules()
        self.parsed_address = self._parse_objects(object_type="address")
        self.parsed_addrgrp = self._parse_objects(object_type="addrgrp")
        self.parsed_servgrp = self._parse_objects(object_type="servgrp")
        self.parsed_service = self._parse_objects(object_type="service")
        self.parsed_usergroup = self._parse_objects(object_type="usergroup")

    def vrf_rules(self, vrf, exclusive=False) -> dict:
        """
        Ищет совпадение имени VRF в значениях правил source/destination interface
        """
        source_vrf_list = []
        destination_vrf_list = []
        address_for_add = []
        addrgrp_for_add = []
        services_for_add = []
        servgrp_for_add = []
        for rule in self.parsed_rules:
            # Ищем где vrf в source
            if rule.get("src_intf") and vrf in rule.get("src_intf"):
                if exclusive:
                    rule["src_intf"] == [vrf]
                source_vrf_list.append(rule)
            # Ищем где vrf в destinaton
            elif rule.get("dst_intf") and vrf in rule.get("dst_intf"):
                if exclusive:
                    rule["dst_intf"] == [vrf]
                destination_vrf_list.append(rule)
        for addresess in [source_vrf_list, destination_vrf_list]:
            data_dict = self._join_objects_from_rules(addresess)
            address_for_add.extend(data_dict.get("address"))
            services_for_add.extend(data_dict.get("services"))
            if "address_group" in data_dict.keys():
                addrgrp_for_add.extend(data_dict.get("address_group"))
            if "servgrp" in data_dict.keys():
                servgrp_for_add.extend(data_dict.get("servgrp"))
        data_for_rule = {
            "vrf_in_source": source_vrf_list,
            "vrf_in_destination": destination_vrf_list,
            "addrgrp": addrgrp_for_add,
            "address": address_for_add,
            "services": services_for_add,
            "servgrp": servgrp_for_add,
        }

        return data_for_rule

    def get_all_addresses(self):
        return self.parsed_address

    def get_all_addrgrp(self):
        return self.parsed_addrgrp

    def get_all_services(self):
        return self.parsed_service

    def get_all_servgrp(self):
        return self.parsed_servgrp

    def get_all_usergroup(self):
        return self.parsed_usergroup

    def get_address_type(self, address_type):
        return [x for x in self.parsed_address if x["object_type"] == address_type]

    def get_service_by_name(self, service_name):
        return [x for x in self.parsed_service if x["name"] == service_name]

    def _parse_rules(self) -> list[dict]:
        """
        Парсит все правила и нормализует каждое в _func
        """
        parse_template = self._template_dict("rule")
        parser = ttp(data=self.config, template=parse_template)
        parser.parse()
        rules_dict = parser.result()[0][0]
        return self._normalize_rule_action(rules_dict)

    def _parse_objects(self, object_type=None) -> list[dict]:
        """
        Парсит объекты - адреса, адресные группы, сервис, сервис группы, юзер группы
        """
        parse_template = self._template_dict(object_type)
        parser = ttp(data=self.config, template=parse_template)
        parser.parse()
        object_dict = parser.result()[0][0]
        # return object_dict
        return self._normalize_object(object_dict, object_type)

    def _join_objects_from_rules(self, parsed_rules: list[dict]) -> dict:
        """
        Функция ищет объекты из правил в списке объектов.
        Те что указаны в правиле собираются в отдельный список для составления правил добавления объектов.
        """
        address_data = []
        address_group_data = []
        addresses = []
        services = []
        services_group_data = []
        services_data = []
        result = {
            "address_group": "",
            "address": "",
            "services": "",
            "servgrp": "",
            "usergroup": "",
        }
        for rule in parsed_rules:
            a = rule.get("src_address") + rule.get("dst_address")
            s = rule.get("dst_service")
            if a:
                addresses = addresses + a
            if s:
                services = services + s
        addresses = list(set(addresses))
        services = list(set(services))
        if not addresses and not services:
            return result
        # Ищем объекты в названиях групп
        # for group in self.parsed_addrgrp:
        #    group: dict
        #    if group.get("name") in addresses:
        #        address_group_data.append(group)
        #        addresses.remove(group.get("name"))
        address_group_data, addresses = self._group_search_with_recursion(
            addresses, group_type="address"
        )

        # объекты из групп добавим в общий список
        if address_group_data:
            result["address_group"] = address_group_data
            addresess_in_group = [
                i for x in address_group_data for i in x.get("members")
            ]

            addresses.extend(addresess_in_group)
        for address in list(set(addresses)):
            if address == "all":
                address_data.append({"name": address})
            for x in self.parsed_address:
                if x.get("name") == address:
                    address_data.append(x)
        # Далее сервисы
        services_group_data, services = self._group_search_with_recursion(
            services, group_type="service"
        )
        if services_group_data:
            result["servgrp"] = services_group_data
            services_in_group = [
                i for x in services_group_data for i in x.get("members")
            ]
            services.extend(services_in_group)
        for x in list(set(services)):
            if x in ["ALL", "ALL_ICMP"]:
                services_data.append({"name": x})
            for serv in self.parsed_service:
                if serv.get("name") == x:
                    services_data.append(serv)
        # rprint(f"[blue]{services_data}")
        # rprint(f"[green]{services_group_data}")
        result["services"] = services_data
        result["address"] = address_data
        return result

    def _group_search_with_recursion(
        self, group_list: list, group_type=None
    ) -> tuple[list]:
        tag = True
        group_data = []
        if group_type == "address":
            search_in = self.parsed_addrgrp
        elif group_type == "service":
            search_in = self.parsed_servgrp
        while tag:
            group_trigger = []
            for group in search_in:
                group: dict
                if group.get("name") in group_list:
                    group_trigger.append(group)
                    group_list.remove(group.get("name"))
                    group_list.extend(group.get("members"))
            if group_trigger:
                group_data.extend(group_trigger)
            else:
                tag = False
        return group_data, group_list

    @staticmethod
    def _template_dict(type: str) -> str:
        """
        Функция-фабрика шаблонов, по типу ищет шаблон парсера, открывает его и передает функции-парсеру
        """
        address_parser = Path(template_directory, "ttp_address_parser.ttp")
        rule_parser = Path(template_directory, "ttp_rule_parser.ttp")
        addrgrp_parser = Path(template_directory, "ttp_addrgrp_parser.ttp")
        service_parser = Path(template_directory, "ttp_service_parser.ttp")
        servgrp_parser = Path(template_directory, "ttp_servgrp_parser.ttp")
        usergroup_parser = Path(template_directory, "ttp_usergroup_parser.ttp")
        template_data = {
            "address": address_parser,
            "rule": rule_parser,
            "addrgrp": addrgrp_parser,
            "service": service_parser,
            "servgrp": servgrp_parser,
            "usergroup": usergroup_parser,
        }
        with open(template_data.get(type), "r") as _f:
            ttp_parser = _f.read()
        return ttp_parser

    @staticmethod
    def _normalize_object(parsed_object: dict, object_type: str) -> list[dict]:
        """Убирает кавычки у строк и превращает список в список списков"""
        objects: list[dict] = parsed_object.get(object_type)
        for object in objects:
            for key, value in object.items():
                if isinstance(value, list) and key != "name":
                    new_value = value[0].split(" ")
                    strip_value = [i.strip('"') for i in new_value]
                    object[key] = strip_value
            if "prefix" in object.keys() and "object_type" not in object.keys():
                object["object_type"] = "prefix"
        return objects

    @staticmethod
    def _normalize_rule_action(parsed_rules: dict) -> list[dict]:
        """Убирает кавычки у строк и превращает список в список списков
        Добавляет ключ значение для deny правил.
        """
        rules = parsed_rules.get("rules")
        for rule in rules:
            # добавляет действие deny которого нет в конфиге
            rule: dict
            if "rule_action" not in rule.keys():
                rule |= {"rule_action": "deny"}
            # превращает вложенные списки в список спиков и отрезает кавычки
            for key, value in rule.items():
                if isinstance(value, list):
                    new_value = value[0].split('" ')
                    strip_value = [i.strip('"') for i in new_value]
                    rule[key] = strip_value
        return rules


if __name__ == "__main__":
    file = "test_rule.txt"
    file = "fg-conf.txt"
    with open(file, "r", encoding="utf-8") as f:
        config = f.read()
    parsed_res = FortiParser(config)
    data = parsed_res.get_all_addresses()
    # data = parsed_res.vrf_rules("VRF_SRV-INT-SER").get("addrgrp")
    for d in data:
        if d.get("object_type") == "iprange":
            print(d)
