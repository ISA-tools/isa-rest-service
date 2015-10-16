# isa-rest-api

RESTful web service to interact with ISA API. Separating out the web service from the programmable API.

Needs to import isatools package from [isa-api project](https://github.com/ISA-tools/isa-api)

Basically to test directly, make sure you've got the right prereqs installed:

`pip install -r files/requirements.txt`
in `isarestapi/config.py` set `UPLOAD_FOLDER` to somewhere sensible (e.g. `/tmp/` - it stores just temporary files for
the conversion.

then:

`python app.py` to start flask's embedded server, and browse. 
`localhost:5000/api/spec.html` for swagger UI (Swagger documentation not yet complete)
`localhost:5000/api/spec.json` for swagger JSON

or load into PyCharm and play with the test_rest_api.py tests

# Usage
## Convert ISArchive (ISA-Tab) archive to ISA-JSON
### `POST /convert/isatab-to-json`
| Consumes              | Produces           | Description    |
| --------------------- |:------------------:| -------------- |
| `application/zip`    | `application/json` |  Takes a ISArchive zip file containing ISA-Tab `.txt` files, converts and returns a single ISA-JSON. Returns 200 OK if succeeded. |

## Convert ISArchive (ISA-JSON) to Tab ISArchive (ISA-Tab) (incomplete, do not use)
### `POST /convert/json-to-isatab`
| Consumes              | Produces              | Description    |
| --------------------- |:---------------------:| -------------- |
| `multipart/form-data` | `multipart/form-data` |  Takes a ISArchive zip file containing a collection of ISA-JSON `.json` files, converts and returns a ISArchive containing ISA-Tab `.txt` files. Returns 200 OK if succeeded.|

### `POST /convert/json-to-isatab`
| Consumes              | Produces              | Description    |
| --------------------- |:---------------------:| -------------- |
| `application/json`    | `application/zip`     |  Takes ISA-JSON content, converts and returns a ISArchive containing ISA-Tab `.txt` files. Returns 200 OK if succeeded. |

## Convert ISArchive (ISA-Tab) to CEDAR JSON
### `POST /convert/isatab-to-cedar`
| Consumes              | Produces              | Description    |
| --------------------- |:---------------------:| -------------- |
| `application/zip    ` | `application/json`    |  Takes a ISArchive zip file containing a collection of ISA-Tab `.txt` files, converts and returns a single CEDAR JSON. Returns 200 OK if succeeded.|

## Create and populate and ISA object, and then get an ISA document (incomplete, do not use)
### `POST /create/`
| Consumes              | Produces              | Description    |
| --------------------- |:---------------------:| -------------- |
| `application/json`    | `application/json`    |  Takes JSON with create parameters (TBC), returns 201 OK and URI of newly created ISA object if succeeded. |

### `PUT /update/{object_id}`
| Consumes              | Produces              | Description    |
| --------------------- |:---------------------:| -------------- |
| `application/json`    | `application/json`    |  Takes JSON with update parameters (TBC), returns 201 OK and URI of updated ISA object if succeeded. |

### `GET /get/{object_id}`
| Consumes              | Produces              | Description    |
| --------------------- |:---------------------:| -------------- |
|                       | `application/json`    |  Returns 200 OK and URI of ISA-JSON representation of ISA object with object ID `{object_id}`. |
