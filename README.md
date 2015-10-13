# isa-rest-api

RESTful web service to interact with ISA API. Separating out the web service from the programmable API.

Needs to import isatools package from [isa-api project](https://github.com/ISA-tools/isa-api)

# Usage (to complete)
## Convert ISA-Tab archive to ISA-JSON
### `POST /isatools/convert/isatab-to-json`
| Consumes              | Produces           | Description    |
| --------------------- |:------------------:| -------------- |
| `application/zip`    | `application/json` |  Takes a ISArchive zip file containing ISA-Tab `.txt` files, converts and returns a single ISA-JSON. Returns 200 OK if succeeded. |

## Convert ISA-JSON to ISA-Tab
### `POST /isatools/convert/json-to-isatab`
| Consumes              | Produces              | Description    |
| --------------------- |:---------------------:| -------------- |
| `multipart/form-data` | `multipart/form-data` |  Takes a ISArchive zip file containing a collection of ISA-JSON `.json` files, converts and returns a ISArchive containing ISA-Tab `.txt` files. Returns 200 OK if succeeded.|

### `POST /isatools/convert/json-to-isatab`
| Consumes              | Produces              | Description    |
| --------------------- |:---------------------:| -------------- |
| `application/json`    | `application/zip`     |  Takes ISA-JSON content, converts and returns a ISArchive containing ISA-Tab `.txt` files. Returns 200 OK if succeeded. |

## Create and populate and ISA object, and then get an ISA document
### `POST /isatools/create/`
| Consumes              | Produces              | Description    |
| --------------------- |:---------------------:| -------------- |
| `application/json`    | `application/json`    |  Takes JSON with create parameters (TBC), returns 201 OK and URI of newly created ISA object if succeeded. |

### `PUT /isatools/update/{object_id}`
| Consumes              | Produces              | Description    |
| --------------------- |:---------------------:| -------------- |
| `application/json`    | `application/json`    |  Takes JSON with update parameters (TBC), returns 201 OK and URI of updated ISA object if succeeded. |

### `GET /isatools/get/{object_id}`
| Consumes              | Produces              | Description    |
| --------------------- |:---------------------:| -------------- |
|                       | `application/json`    |  Returns 200 OK and URI of ISA-JSON representation of ISA object with object ID `{object_id}`. |
