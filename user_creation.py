import urllib3
import argparse
import yaml
import redfish
import json
import logging

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def main() -> None:
    """Main function"""
    # Get the command line arguments from the user.
    parser = argparse.ArgumentParser(description="Create new BMC Users")
    parser.add_argument(
        "-i",
        "--info",
        metavar="info",
        help="path to credential YAML file",
        required=True,
    )
    args = parser.parse_args()
    info_path = args.info
    with open(info_path, "r") as info_path:
        info_dict = yaml.safe_load(info_path)

    for machine in info_dict:
        key_list = list(info_dict[machine].keys())
        if (
            "admin_user" not in key_list
            or "admin_password" not in key_list
            or "new_user" not in key_list
            or "new_password" not in key_list
        ):
            raise Exception(
                "The YAML for "
                + machine
                + " is formatted incorrectly. Each machine should include the 'admin_user', 'admin_password', "
                + "'new_user', and 'new_password' subfields, as shown in example.yml"
            )
        base_url = "https://" + machine
        REDFISH_OBJ = redfish.redfish_client(
            base_url=base_url,
            username=info_dict[machine]["admin_user"],
            password=info_dict[machine]["admin_password"],
            default_prefix="/redfish/v1",
        )
        REDFISH_OBJ.login(auth="session")
        system_summary = REDFISH_OBJ.get("/redfish/v1/Systems")
        system_url = json.loads(system_summary.text)["Members"][0]["@odata.id"]
        system_json = json.loads(REDFISH_OBJ.get(system_url).text)
        manufacturer = system_json["Manufacturer"]
        if "hp" in manufacturer.lower():
            # There are differences between iLO 4 and iLO 5. Retrieve the iLO version
            # of each machine and alter the body variable accordingly
            body = {
                "UserName": info_dict[machine]["new_user"],
                "Password": info_dict[machine]["new_password"],
            }

            # Assume iLO 5
            ilo_version = 5
            if "Links" in system_json:
                manager_url = system_json["Links"]["ManagedBy"][0]["@odata.id"]
            elif "links" in system_json:
                manager_url = system_json["links"]["ManagedBy"][0]["href"]
            if manager_url:
                manager_json = json.loads(REDFISH_OBJ.get(manager_url).text)
                ilo_version = int(manager_json["FirmwareVersion"][4])
            if ilo_version == 5:
                body["RoleId"] = "ReadOnly"
            else:
                body["Oem"] = {"Hp": {"Privileges": {"LoginPriv": True}}}
                body["Oem"]["Hp"]["LoginName"] = info_dict[machine]["new_user"]
            new_account = REDFISH_OBJ.post(
                "/redfish/v1/AccountService/Accounts", body=body
            )
        else:
            body = {
                "UserName": info_dict[machine]["new_user"],
                "Password": info_dict[machine]["new_password"],
                "RoleId": "ReadOnly",
                "Enabled": True,
            }
            if "dell" in manufacturer.lower():
                # Go through accounts and if ID doesn't have username, add account to that ID.
                dell_accounts = REDFISH_OBJ.get(
                    "/redfish/v1/Managers/iDRAC.Embedded.1/Accounts/"
                )
                if "Members" in dell_accounts.text:
                    for account in json.loads(dell_accounts.text)["Members"]:
                        account_info = REDFISH_OBJ.get(account["@odata.id"])
                        account_json = json.loads(account_info.text)
                        if not account_json["UserName"] and account_json["Id"] != "1":
                            id = account_json["Id"]
                            break
                    new_account = REDFISH_OBJ.patch(
                        "/redfish/v1/Managers/iDRAC.Embedded.1/Accounts/{}".format(id),
                        body=body,
                    )
            else:
                new_account = REDFISH_OBJ.post(
                    "/redfish/v1/AccountService/Accounts", body=body
                )

        if "error" in new_account.text:
            try:
                response = json.loads(new_account.text)
                if "Message" in response["error"]["@Message.ExtendedInfo"][0]:
                    logging.warning(
                        "The '{}' account for {} was NOT created due to an error: ".format(
                            info_dict[machine]["new_user"], machine
                        )
                        + response["error"]["@Message.ExtendedInfo"][0]["Message"]
                    )
                else:
                    logging.warning(
                        "The '{}' account for {} was NOT created due to an error: ".format(
                            info_dict[machine]["new_user"], machine
                        )
                        + response["error"]["@Message.ExtendedInfo"][0]["MessageId"]
                    )
            except:
                logging.warning(
                    "The '{}' account for {} was NOT created due to an error, and the resulting error message was not parsable by the script.".format(
                        info_dict[machine]["new_user"], machine
                    )
                )
        else:
            print(
                "The '{}' account for {} was created successfully.".format(
                    info_dict[machine]["new_user"], machine
                )
            )

        REDFISH_OBJ.logout()


# Executes main if run as a script.
if __name__ == "__main__":
    main()
