# wilkloud-engine

The backend service for **Wilkloud**, a self-hosted media server alternative that integrates with [Sonarr](https://sonarr.tv/) and [Radarr](https://radarr.video/) for managing TV shows and movies.

## Prerequisites

To run `wilkloud-engine`, ensure you have the following installed:

* Python 3.10+
* [Sonarr](https://sonarr.tv/) and/or [Radarr](https://radarr.video/) running
* [Redis](https://redis.io/)

## Setup Instructions

1. **Clone the repository**

   ```bash
   git clone https://github.com/jlwilk/wilkloud-engine.git
   cd wilkloud-engine
   ```

2. **Install dependencies**

   ```bash
   pip install -r requirements.txt
   ```

3. **Configure environment variables**

   * Copy the example env file:

     ```bash
     cp .env.example .env
     ```

   * Set the following values in your `.env` file:

     * `SONARR_API_KEY` (if using Sonarr)
     * `RADARR_API_KEY` (if using Radarr)
     * `REDIS_HOST` (e.g., `localhost` or Docker service name)

4. **Run the server**

   ```bash
   uvicorn app.main:app --reload
   ```

5. **Read the api docs**

    [API Docs](http://localhost:8000/docs#/)

## Notes

* The API keys for Sonarr/Radarr are available in their respective web UIs under **Settings > General > Security**.
* Redis is used for caching or background task queuing. You must have it running and accessible.

## TODO

* [ ] Add Docker support
* [ ] Add tests and CI/CD config
* [ ] Improve API documentation
* [ ] Add OAuth or user authentication
