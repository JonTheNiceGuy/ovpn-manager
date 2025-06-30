# OVPN Manager

OVPN Manager is a secure web application for dynamically generating user- and device-specific OpenVPN profiles based on authentication and group membership from an OIDC provider.

It provides a seamless workflow for both users downloading their own profiles via a browser and a CLI client for automated or headless configuration retrieval. The system is designed to be deployed as a hardened, scalable service on Kubernetes via a Helm chart.

## Features

* **OIDC Integration:** Securely delegates user authentication to any OpenID Connect compliant provider.
* **Group-Based Configuration:** Dynamically selects OVPN templates based on a user's OIDC group memberships, allowing for different profiles for different teams (e.g., Engineering vs. IT).
* **Dynamic Templating:** Uses Jinja2 to render templates, allowing for rich, user-specific data (name, email, etc.) to be embedded in the final configuration file.
* **Kubernetes Native:** Templates are managed via a Kubernetes ConfigMap, allowing for on-the-fly updates without redeploying the application.
* **Database Backend:** Uses a PostgreSQL or SQLite backend to store auditable records of every token issued.
* **Robust Security:**
    * **Encryption at Rest:** All sensitive OVPN profile data is encrypted in the database.
    * **Defense-in-Depth:** Implements rate limiting, security headers (via Talisman), non-root containers with read-only filesystems, and server-side sessions.
* **Admin Dashboard:** A protected `/admin/status` page for authorized users to view and filter a complete history of issued tokens.
* **CLI and Browser Flows:** Supports both a fully automated CLI client and a user-friendly, browser-based download flow.
* **Automated Deployments:** Includes a comprehensive Helm chart for easy, configurable, and repeatable deployments, including automated database migrations via Helm Hooks.
* **Test Suite:** A thorough `pytest` suite provides high confidence in the application's functionality, security, and robustness. Please see later in this file for the recognised testing exclusions.

## Technology Stack

* **Backend:** Python 3, Flask
* **Database:** SQLAlchemy ORM, Flask-Migrate (Alembic), PostgreSQL (production), SQLite (local/test)
* **Authentication:** OIDC (via `authlib`)
* **Deployment:** Docker, Gunicorn, Kubernetes, Helm
* **Security:** Flask-Talisman, Flask-Limiter, Fernet (cryptography)
* **Client:** Python, Click, PyYAML, platformdirs

## Project Structure

```
.
├── client/                 # The Python CLI client application
├── migrations/             # Flask-Migrate (Alembic) database migration scripts
├── ovpn-manager/           # Helm chart for Kubernetes deployment
├── server/                 # The main Flask server application package,
│   │                       #   including blueprints for admin, auth, main routes, etc.
│   └── templates/          # HTML templates for the application
├── tests/                  # Pytest suite
├── .coveragerc             # Configuration for test coverage reporting
├── .envrc                  # Example environment file for local development
├── Dockerfile              # Dockerfile for building the server image
└── dev/                    # Files used to support local development work
    └── generate_ca.py      # Script to generate a dummy CA for local dev

```

## Local Development Setup

1.  **Clone the Repository:**
    ```bash
    git clone <your-repo-url>
    cd ovpn-manager
    ```

2.  **Set up Virtual Environment:**
    ```bash
    python3 -m venv .venv
    source .venv/bin/activate
    pip install -r server/requirements.txt -r client/requirements.txt -r tests/requirements.txt
    ```

3.  **Create Local Configuration:**
    * The default `.envrc` is configured to use a local SQLite database and dummy keys, which is sufficient for most development tasks.

4.  **Generate Local CA:**
    * Run the generation script once to create dummy certificates for local use.
    * ```bash
        python generate_ca.py
        ```

5.  **Initialize and Upgrade the Database:**
    * Make sure your `.env` file is present.
    * ```bash
        export FLASK_APP=server:create_app()
        flask db upgrade
        ```

6.  **Run the Development Server:**
    * ```bash
        flask run
        ```
    * The application will be available at `http://127.0.0.1:5000`.

## Production Deployment (Kubernetes & Helm)

The application is designed to be deployed using the included Helm chart.

1.  **Prerequisites:** A running Kubernetes cluster, Helm, `kubectl`, a configured container registry, a PostgreSQL database, and a registered OIDC client application.
2.  **Build and Push Image:** Build the `ovpn-manager` image using the `Dockerfile` and push it to your container registry.
3.  **Configure Values:** Create a `values-prod.yaml` file to override the defaults in `values.yaml`. It is critical to configure your database URL and OIDC client details here.
4.  **Manage Secrets:** Provide production secrets (passwords, client secrets, encryption keys) securely during deployment, for example using `--set` flags or a secrets backend like Vault.
5.  **Deploy:** Run `helm upgrade --install` to deploy the application. The `pre-upgrade` hook will automatically run any necessary database migrations.

    ```bash
    helm upgrade --install ovpn-manager ./ovpn-manager \
      -n <namespace> \
      -f values-prod.yaml \
      --set secrets.oidc.clientSecret=<your-secret>
    ```

## Testing Strategy

This project uses `pytest` and the `pytest-cov` plugin to maintain high code quality and test coverage. The goal is to ensure all core business logic, models, and routes are thoroughly tested.

### Accepted Coverage Exclusions

* **`server/logging.py`**: This file contains a custom logger class used exclusively by the Gunicorn production server to filter health check probes from the access logs. As our test suite runs the application with Werkzeug's test server, this code is not executed during tests. Its logic is simple and has been verified through manual inspection and by observing the logs in a live deployment environment. It is therefore intentionally excluded from the coverage report.

## Authorship and Origin

This project was developed collaboratively. Initial scaffolding, boilerplate code, and some functional components were generated with the assistance of a large language model (AI).

The training data for such models includes a vast amount of publicly available code, and while the generated code is original in its composition for this project, it is influenced by the work of countless developers. We are committed to respecting the work of the open-source community. If you believe any code in this repository bears a strong, un-attributed resemblance to your own proprietary or licensed work, please raise an issue. We will promptly investigate and attribute or remove the code as appropriate.

## License

This project is licensed under the **GNU Affero General Public License v3.0**. A copy of the license should be included in a `LICENSE` file in this repository. The full license text is available at [https://www.gnu.org/licenses/agpl-3.0.html](https://www.gnu.org/licenses/agpl-3.0.html).
