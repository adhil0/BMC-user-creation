"""Module that creates read-only BMC accounts"""
import argparse

import redfish
import urllib3
import yaml

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def main():
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
    with open(args.info, "r", encoding="utf-8") as info_path:
        info_dict = yaml.safe_load(info_path)

    for machine in info_dict:
        key_list = list(info_dict[machine].keys())
        if (
            "admin_user" not in key_list
            or "admin_password" not in key_list
            or "new_user" not in key_list
            or "new_password" not in key_list
        ):
            raise ValueError(
                "The YAML for "
                + machine
                + " is formatted incorrectly. Each machine should include the "
                + "'admin_user', 'admin_password', "
                + "'new_user', and 'new_password' subfields, as shown in example.yml"
            )
        base_url = f"https://{machine}"
        try:
            redfish_obj = redfish.redfish_client(
                base_url=base_url,
                username=info_dict[machine]["admin_user"],
                password=info_dict[machine]["admin_password"],
                default_prefix="/redfish/v1",
            )
            redfish_obj.login(auth="session")
        except redfish.rest.v1.ServerDownOrUnreachableError:
            print(f"FAILED: {machine} is down or unreachable.")
            continue
        except redfish.rest.v1.RetriesExhaustedError:
            print(f"FAILED: Can't connect to {machine}")
            continue
        except redfish.rest.v1.InvalidCredentialsError:
            print(f"FAILED: Invalid Credentials for {machine}")
            continue
        except redfish.rest.v1.SessionCreationError:
            print(f"FAILED: Failed to create the session for {machine}")
            continue

        system_summary = redfish_obj.get("/redfish/v1/Systems")
        system_url = system_summary.dict["Members"][0]["@odata.id"]
        system_json = redfish_obj.get(system_url).dict
        manufacturer = system_json["Manufacturer"]
        if "hp" in manufacturer.lower():
            new_account = create_hp_account(
                info_dict, machine, system_json, redfish_obj
            )
        else:
            body = {
                "UserName": info_dict[machine]["new_user"],
                "Password": info_dict[machine]["new_password"],
                "Enabled": True,
            }

            if "dell" in manufacturer.lower():
                new_account = create_dell_account(redfish_obj, body)
            else:
                # Get name of read only role
                roles = redfish_obj.get("/redfish/v1/AccountService/Roles")
                try:
                    for role in roles.dict["Members"]:
                        if "readonly" in role["@odata.id"].lower():
                            role_id_index = role["@odata.id"].rfind("/")
                            role_id = role["@odata.id"][role_id_index + 1 :]
                except KeyError:
                    print(f"FAILED: Can't find roles for {machine}")
                    continue
                body["RoleId"] = role_id
                new_account = redfish_obj.post(
                    "/redfish/v1/AccountService/Accounts", body=body, timeout=20
                )

        print_response_messages(new_account, info_dict, machine)

        redfish_obj.logout()


def create_hp_account(info_dict, machine, system_json, redfish_obj):
    """Create BMC account for HP machines

    Args:
        info_dict (dict): Contains root and new account information
        machine (string): IP of machine
        system_json (dict): Basic information about machine
        redfish_obj (redfish): Redfish session object

    Returns:
        redfish.rest.v1.RestResponse: Response after attempting to create account.
    """
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
        manager_json = redfish_obj.get(manager_url).dict
        ilo_version = int(manager_json["FirmwareVersion"][4])
    if ilo_version == 5:
        body["RoleId"] = "ReadOnly"
    else:
        body["Oem"] = {"Hp": {"Privileges": {"LoginPriv": True}}}
        body["Oem"]["Hp"]["LoginName"] = info_dict[machine]["new_user"]

    new_account = redfish_obj.post("/redfish/v1/AccountService/Accounts", body=body)

    return new_account


def create_dell_account(redfish_obj, body):
    """Create BMC account for Dell machines

    Args:
        redfish_obj (redfish): Redfish session object
        body (dict): Information about account for patch request

    Returns:
        redfish.rest.v1.RestResponse: Response after attempting to create account
    """
    # Go through accounts and if ID doesn't have username,
    # add account to that ID.
    body["RoleId"] = "ReadOnly"
    dell_accounts = redfish_obj.get("/redfish/v1/Managers/iDRAC.Embedded.1/Accounts/")
    if "Members" in dell_accounts.dict:
        for account in dell_accounts.dict["Members"]:
            account_info = redfish_obj.get(account["@odata.id"])
            account_json = account_info.dict
            if not account_json["UserName"] and account_json["Id"] != "1":
                available_id = account_json["Id"]
                break
        new_account = redfish_obj.patch(
            f"/redfish/v1/Managers/iDRAC.Embedded.1/Accounts/{available_id}",
            body=body,
            timeout=20,
        )
    return new_account


def print_response_messages(new_account, info_dict, machine):
    """Print the response messages after attempting to create read only accounts

    Args:
        new_account (redfish.rest.v1.RestResponse): Response of account creation
        info_dict (dict): Contains root and new account information
        machine (string): IP of machine
    """
    if "error" in new_account.text:
        try:
            response = new_account.dict
            if "Message" in response["error"]["@Message.ExtendedInfo"][0]:
                print(
                    (
                        f"FAILED: The '{info_dict[machine]['new_user']}' account "
                        f"for {machine} was NOT created due to an error: "
                        f"{response['error']['@Message.ExtendedInfo'][0]['Message']}"
                    )
                )
            else:
                print(
                    (
                        f"FAILED: The '{info_dict[machine]['new_user']}' account "
                        f"for {machine} was NOT created due to an error: "
                        f"{response['error']['@Message.ExtendedInfo'][0]['MessageId']}"
                    )
                )
        except:
            print(
                (
                    f"FAILED: The '{info_dict[machine]['new_user']}' account "
                    f"for {machine} was NOT created due to an error, and the "
                    "resulting error message was not parsable by the script."
                )
            )
    else:
        print(
            (
                f"The '{info_dict[machine]['new_user']}' account for "
                f"{machine} was created successfully."
            )
        )


# Executes main if run as a script.
if __name__ == "__main__":
    main()
