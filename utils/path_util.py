import os


def maven_to_path(maven_name: str, to_path: str) -> dict["name": str, "var": str, "lib_name": str, "lib_sub_path": str, "path": str, ]:
    lib_path = maven_name.split(":")
    lib_name = f"{lib_path[1]}-{lib_path[2]}.jar"

    lib_sub_path = "/".join(lib_path[0].split("."))
    path = f".minecraft/assets/libraries/{lib_sub_path}/{lib_path[1]}/{lib_path[2]}"
    return {
        "name": lib_path[1],
        "var": lib_path[2],
        "lib_name": lib_name,
        "lib_sub_path": lib_sub_path,
        "path": os.path.join(to_path, lib_sub_path, lib_path[1], lib_path[2])
    }