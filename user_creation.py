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
    parser.add_argument(
        "-m",
        "--modify",
        action="store_true",
        help="Use this flag to modify account password",
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
        if args.modify:
            new_account = modify_accounts(system_json, redfish_obj, info_dict, machine)
        else:
            try:
                new_account = create_accounts(system_json, redfish_obj, info_dict, machine)
            except KeyError as key_error:
                print(f"FAILED: The '{info_dict[machine]['new_user']}' account "
                f"for {machine} was NOT created due to a KeyError: {key_error}")
                continue
        print_response_messages(new_account, info_dict, machine)

        redfish_obj.logout()


def modify_accounts(system_json, redfish_obj, info_dict, machine):
    """Modify a pre-existing account's password

    Args:
        system_json (dict): Basic information about machine
        redfish_obj (redfish): Redfish session object
        info_dict (dict): Contains root and new account information
        machine (string): IP of machine

    Returns:
        redfish.rest.v1.RestResponse: Response after attempting to modify an account.
    """
    manufacturer = system_json["Manufacturer"]
    if "dell" in manufacturer.lower():
        new_account = modify_dell_account(info_dict, machine, redfish_obj)
    else:
        new_account = modify_generic_account(info_dict, machine, redfish_obj)
    return new_account


def create_accounts(system_json, redfish_obj, info_dict, machine):
    """Create an account

    Args:
        system_json (dict): Basic information about machine
        redfish_obj (redfish): Redfish session object
        info_dict (dict): Contains root and new account information
        machine (string): IP of machine

    Returns:
        redfish.rest.v1.RestResponse: Response after attempting to create an account.
    """
    manufacturer = system_json["Manufacturer"]
    if "hp" in manufacturer.lower():
        new_account = create_hp_account(info_dict, machine, system_json, redfish_obj)
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
                return None
            body["RoleId"] = role_id

            new_account = redfish_obj.post(
                "/redfish/v1/AccountService/Accounts", body=body, timeout=20
            )
    return new_account


def modify_generic_account(info_dict, machine, redfish_obj):
    """Modify a pre-existing account for machines that don't need manufacturer specific
    code

    Args:
        info_dict (dict): Contains root and new account information
        machine (string): IP of machine
        redfish_obj (redfish): Redfish session object

    Returns:
        redfish.rest.v1.RestResponse: Response after attempting to modify an account.
    """
    body = {
        "Password": info_dict[machine]["new_password"],
    }
    username = info_dict[machine]["new_user"]
    user_id = get_user_id(redfish_obj, username)
    if user_id is not None:
        new_account = redfish_obj.patch(
            f"/redfish/v1/AccountService/Accounts/{user_id}", body=body
        )
        return new_account

    return None


def get_user_id(redfish_obj, username):
    """Get the ID of the relevant account

    Args:
        redfish_obj (redfish): Redfish session object
        username (string): username of the relevant account

    Returns:
        string: ID of the relevant account
    """
    users = redfish_obj.get("/redfish/v1/AccountService/Accounts")
    for user in users.dict["Members"]:
        user_info = redfish_obj.get(user["@odata.id"])
        if user_info.dict["UserName"] == username:
            return user_info.dict["Id"]

    print("FAILED: User doesn't exist")
    return None


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
    if ilo_version == 5 or ilo_version == 6:
        body["RoleId"] = "ReadOnly"
    else:
        body["Oem"] = {"Hp": {"Privileges": {"LoginPriv": True}}}
        body["Oem"]["Hp"]["LoginName"] = info_dict[machine]["new_user"]

    new_account = redfish_obj.post("/redfish/v1/AccountService/Accounts", body=body)

    return new_account


def modify_dell_account(info_dict, machine, redfish_obj):
    """Change the password of a dell account

    Args:
        info_dict (dict): Contains root and new account information
        machine (string): IP of machine
        redfish_obj (redfish): Redfish session object

    Returns:
        redfish.rest.v1.RestResponse: Response after attempting to modify an account.
    """
    body = {
        "Password": info_dict[machine]["new_password"],
    }
    username = info_dict[machine]["new_user"]
    user_id = get_dell_user_id(redfish_obj, username)
    if user_id is not None:
        new_account = redfish_obj.patch(
            f"/redfish/v1/Managers/iDRAC.Embedded.1/Accounts/{user_id}", body=body
        )
        return new_account

    return None


def get_dell_user_id(redfish_obj, username):
    """Get the ID of the relevant dell account

    Args:
        redfish_obj (redfish): Redfish session object
        username (string): username of the relevant dell account

    Returns:
        string: ID of the relevant dell account
    """
    dell_accounts = redfish_obj.get("/redfish/v1/Managers/iDRAC.Embedded.1/Accounts/")
    if "Members" in dell_accounts.dict:
        for account in dell_accounts.dict["Members"]:
            account_info = redfish_obj.get(account["@odata.id"])
            if account_info.dict["UserName"] == username:
                return account_info.dict["Id"]

        print(f"FAILED: User doesn't exist for {redfish_obj.get_base_url()}")
    return None


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
    if new_account is not None:
        error_messages = redfish.messages.get_error_messages(new_account)
        if (
            error_messages
            and "The request completed successfully." not in error_messages
        ):
            print(
                f"FAILED: The '{info_dict[machine]['new_user']}' account "
                f"for {machine} was NOT created due to an error: {error_messages}"
            )
        else:
            print(
                (
                    f"The '{info_dict[machine]['new_user']}' account for "
                    f"{machine} was created and/or modified successfully."
                )
            )


# Executes main if run as a script.
if __name__ == "__main__":
    main()
