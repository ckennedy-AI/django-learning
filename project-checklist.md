Checklist 1: Project Setup
* Create a virtual environment and install Django, Django REST Framework, celery, redis, and hiredis
* Start a project and create at least one app inside it
* Register the app and rest_framework in INSTALLED_APPS
* Identify the roles of manage.py, settings.py, root urls.py, wsgi.py, and asgi.py
* Move SECRET_KEY, DEBUG, and database credentials out of settings.py into environment variables
* Load environment variables with django-environ, using env.db() and env.cache() for connection URLs
* Pin dependencies in a requirements file
* Initialize the repo with a .gitignore and a main to dev to feature branch workflow
* Run the dev server and confirm the project boots

Checklist 2: Containerized Development Environment
* Write a Dockerfile for the Django app
* Add a docker compose setup that runs the app, the database, and Redis
* Use the pgvector/pgvector:pg17 image for the database service
* Point Django at the containerized Postgres and Redis through environment variables, with Redis serving both the cache and the Celery broker
* Persist database data with a named volume
* Add a named volume for the Hugging Face model cache so the embedding model is not re-downloaded on every rebuild
* Add a healthcheck to the database service and make the app wait for it to pass
* Add a .dockerignore and keep the image lean
* Run manage.py commands inside the container
* Document the commands to bring the environment up, down, and rebuild

Checklist 3: Models & Schema Design
* Implement a custom user model extending AbstractUser and set AUTH_USER_MODEL before running the first migration
* Define at least four related models using ForeignKey, OneToOneField, and ManyToManyField
* Add a self-referential ForeignKey for the reporting hierarchy
* Use a mix of field types including choices, null, blank, unique, and defaults
* Add __str__ and Meta ordering to every model
* Set on_delete deliberately on each relationship and be able to explain the choice
* Add related_name to every relationship
* Add a model method and a model property that derive values from fields
* Add a custom manager or queryset that holds reusable filters
* Add a vector column to one model for embeddings
* Add db_index to fields that will be filtered often
* Add a composite Meta index covering fields that are filtered and ordered together
* Add an HNSW index on the embedding column
* Add a unique constraint and a check constraint through Meta
* Enable the pgvector extension through an empty migration using VectorExtension, the one documented exception to writing no migrations by hand
* Run makemigrations and migrate, then open and read the generated migration file
* Add a field to an existing model and migrate again
* Use makemigrations for every other schema change

Checklist 4: Django Admin
* Create a superuser and log into the admin
* Register all models
* Customize one ModelAdmin with list_display, list_filter, and search_fields
* Add readonly_fields and date_hierarchy where they make the data easier to read
* Add list_select_related to an admin to avoid N+1 queries in the list view
* Use an inline to edit a related model from its parent
* Inspect and correct data through the admin rather than through an API client

Checklist 5: The ORM & Querying
* Load 100,000 or more rows of realistic sample data through a management command
* Practice filter, exclude, get, order_by, count, values, and values_list in the shell
* Query backwards across a relationship using related_name
* Write queries that span relationships using double-underscore lookups
* Use Q objects for OR conditions and F expressions for field-to-field comparisons
* Use annotate and aggregate to push calculations into the database
* Use only and defer to limit the columns returned
* Use bulk_create, bulk_update, and update_or_create for high-volume writes
* Use iterator() on a queryset too large to hold in memory
* Write a "latest record per group" query, first the naive way and then with distinct on a field or a window function
* Trigger an N+1 query, then fix it with select_related and prefetch_related
* Inspect the generated SQL with .query and run EXPLAIN ANALYZE on the slowest query
* Confirm from a query plan that an index you added is actually being used
* Shape values() and values_list() output into plain dicts ready for a JSON response
* Run a similarity query against the vector column

Checklist 6: URLs, Views, Serializers & the Service Layer
* Read HackSoft's argument against ModelViewSet and generics, then set the project's convention
* Adopt a consistent API naming convention such as <Entity><Action>Api, with one URL per action
* Wire app URLs into the root urls.py using include()
* Name every URL and reference names rather than hardcoded paths
* Add a URL that captures a path parameter and passes it to the view
* Build one APIView per endpoint with explicit get and post handlers
* Return responses with DRF Response and correct status codes
* Build separate input and output serializers, nested inside the API class rather than shared
* Validate query parameters with an input serializer, including an upper bound on any limit parameter
* Decide and document how invalid input is handled, whether a 4xx response or a safe default
* Create a selectors module for read queries
* Create a services module for writes and business logic
* Route every view through a service or selector rather than touching the ORM directly
* Keep views limited to request handling, input validation, and response shaping
* Write one service function that coordinates multiple models in a single operation
* Wrap multi-step writes in transaction.atomic
* Define a custom application exception and translate it to an HTTP status in one place through a custom DRF exception handler
* Confirm business logic lives in services and selectors, not in serializers or views

Checklist 7: Endpoint Design & Performance
* Split list and detail into separate endpoints rather than one flexible view
* Create separate endpoints for different data slices of the same model, such as the full object versus one related subset versus another
* Avoid the pattern of one bulky endpoint driven by many optional filter parameters
* Add DRF pagination to every list endpoint through a get_paginated_response helper, since plain APIView does not paginate automatically
* Validate filter parameters with a nested FilterSerializer and perform the actual filtering inside selectors
* Return only the fields each endpoint actually needs, avoiding fetching related data an endpoint does not use
* Apply select_related and prefetch_related deliberately, per endpoint
* Measure the cost of a many-to-many read before exposing it through an endpoint
* Audit query counts per endpoint with assertNumQueries, using Django Debug Toolbar through the DRF browsable API where it renders
* Record the expected usage volume of each endpoint and the optimization level it justifies
* Build one high-traffic dashboard style endpoint and optimize it tightly
* Leave one low-traffic endpoint unoptimized on purpose and note the tradeoff
* Compare DRF PageNumberPagination against CursorPagination on a deep page of a large table
* Add or adjust indexes based on the filters the endpoints actually use
* Cache one expensive endpoint in Redis and measure the difference
* Define a cache key strategy and an invalidation trigger for the cached endpoint
* Benchmark before and after each optimization rather than assuming it helped

Checklist 8: Authentication & Authorization
* Configure djangorestframework-simplejwt for access and refresh tokens
* Set SIGNING_KEY from its own environment variable rather than reusing SECRET_KEY
* Add token obtain and token refresh endpoints
* Set access and refresh token lifetimes deliberately
* Enable ROTATE_REFRESH_TOKENS and BLACKLIST_AFTER_ROTATION with the token_blacklist app installed
* Set DRF default authentication and permission classes in settings
* Protect DRF endpoints with authentication and permission classes
* Attach a record to request.user on creation
* Scope read queries inside selectors so users only see their own records
* Add an object-level permission check on a detail endpoint
* Exercise the full refresh flow from an API client, including an expired access token
* Add DRF throttling backed by Redis on the auth endpoints
* Confirm no session-based login or logout views remain in the project
* Experiment with two-factor authentication on login (stretch goal, only if time allows)

Checklist 9: Celery & Background Jobs
* Configure a Celery app with Redis as broker and result backend
* Add Celery worker and beat services to docker compose
* Move one slow operation out of the request cycle into a task
* Trigger a task from a service function and return a response immediately
* Enqueue tasks with transaction.on_commit so a worker never reads uncommitted data
* Pass IDs as task arguments rather than model instances, and understand why
* Store and retrieve a task result
* Configure retries with backoff on a task that can fail
* Make one task idempotent and safe to run twice
* Add a periodic task with Celery beat
* Set task time limits and route one task to a dedicated queue
* Inspect workers and queues with Flower or the Celery CLI

Checklist 10: Testing
* Configure the test database to run against the containerized Postgres
* Point tests at a separate Redis database or the local memory cache
* Write model tests covering methods, properties, and constraints
* Write unit tests for service and selector functions, called directly rather than through a view
* Write integration tests for each endpoint covering success and failure paths
* Test query parameter edge cases including missing, empty, non-numeric, and above-maximum values
* Write tests that verify authentication and permission enforcement
* Use assertNumQueries to lock in query counts on the optimized endpoints
* Add reusable test data through factories or fixtures
* Test Celery tasks with CELERY_TASK_ALWAYS_EAGER, and by calling the task function directly
* Use captureOnCommitCallbacks so transaction.on_commit tasks actually fire under TestCase
* Run the suite and make one test fail on purpose to read the output
* Trace a single request end to end: URL to view to service to model to response
* Leave custom middleware and multi-tenant testing out of scope

Checklist 11: CI/CD with GitHub Actions
* Add a workflow that runs on push and on pull request
* Build the Docker image in CI
* Spin up a pgvector/pgvector:pg17 service container for the test job
* Spin up a Redis service container for the test job
* Add health check options to both service containers
* Run migrations and the test suite in CI
* Add linting and formatting checks
* Cache dependencies to keep runs fast
* Require the workflow to pass before merging into dev
* Add a deploy step to see the full pipeline, even against a stub environment
* Add a status badge to the README

Checklist 12: Documentation & Wrap-Up
* Write a README covering setup, environment variables, and Docker commands
* Document every endpoint, its purpose, and its expected usage volume
* Document each Celery task, its schedule, its queue, and its retry behavior
* Maintain a CLAUDE.md with the domain, models, conventions, and usage expectations to give Claude up front
* Write a short summary in this card of how Django's request cycle fits together, from URL to response
* Add drf-spectacular OpenAPI docs, decorating each APIView with extend_schema (deferred, after the initial deadline)