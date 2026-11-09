# Bulk Music Downloader

**A sequential, resumable bulk audio downloader built with Python.**

Bulk Music Downloader is a command-line application I built to make
downloading authorized audio files in batches more manageable.

Instead of searching for tracks, downloading them individually, and
manually keeping track of what has already been downloaded, I wanted a
system that could manage a music queue, search multiple sources,
evaluate matching results, handle downloads sequentially, recover from
interruptions, and preserve download history.

This project is my attempt to turn that idea into a practical,
extensible application.

**Developer:** Derrick\
**Project:** Bulk Music Downloader\
**Current version:** `v0.1.0`\
**Primary platform:** Ubuntu Linux\
**Language:** Python 3.10+\
**Interface:** Command-line application\
**License:** Not yet formally selected

------------------------------------------------------------------------

## Table of Contents

-   [1. Project Vision](#1-project-vision)
-   [2. What I Have Built](#2-what-i-have-built)
-   [3. Provider Support](#3-provider-support)
-   [4. How the Application Works](#4-how-the-application-works)
-   [5. Requirements](#5-requirements)
-   [6. Installation](#6-installation)
-   [7. Configuration](#7-configuration)
-   [8. Preparing a Music Queue](#8-preparing-a-music-queue)
-   [9. Using the Application](#9-using-the-application)
-   [10. Command Reference](#10-command-reference)
-   [11. Queue and Download
    Management](#11-queue-and-download-management)
-   [12. Data Storage and Recovery](#12-data-storage-and-recovery)
-   [13. Matching and Download Safety](#13-matching-and-download-safety)
-   [14. Testing and Validation](#14-testing-and-validation)
-   [15. Development Progress](#15-development-progress)
-   [16. What I Still Want to Build](#16-what-i-still-want-to-build)
-   [17. Known Limitations](#17-known-limitations)
-   [18. Troubleshooting](#18-troubleshooting)
-   [19. Project Structure](#19-project-structure)
-   [20. Developer](#20-developer)

------------------------------------------------------------------------

# 1. Project Vision

I started Bulk Music Downloader with a straightforward objective:

**Make bulk downloading of authorized music more organized, reliable,
and manageable.**

I did not want a script that simply downloads files and exits. I wanted
an application capable of maintaining its state, managing a large queue,
handling failures, and continuing work after interruptions.

My broader vision is to develop it into a dependable personal audio
acquisition and management tool.

The main engineering objectives are:

1.  Import large lists of songs.
2.  Search multiple audio sources.
3.  Find relevant matches using title and artist information.
4.  Avoid downloading unrelated or unverified results.
5.  Download tracks sequentially.
6.  Retry failed operations and fall back to other providers.
7.  Preserve download history independently of the active queue.
8.  Recover interrupted operations.
9.  Allow users to review and manage their queues.
10. Build an extensible provider architecture.

I prioritize reliability and responsible source integration over
downloading as many files as possible.

------------------------------------------------------------------------

# 2. What I Have Built

Version `0.1.0` is the first substantial release of the multi-source
downloader.

It includes the following functionality.

### Queue management

-   Import songs from TXT and CSV files.
-   Support multiple text-file entry formats.
-   Replace the active queue when importing a new list.
-   Preserve historical download records when replacing a queue.
-   Track pending, searching, downloading, completed, failed, skipped,
    and interrupted work.
-   Review the active queue.

### Multi-source architecture

The application has a provider-based architecture.

It currently registers:

-   Audius
-   Jamendo
-   FreeToUse
-   ccMixter
-   Internet Archive
-   Direct URL

Each provider has its own integration logic and availability
limitations.

### Matching engine

-   Search using track title and artist.
-   Fall back to title-only searches where supported.
-   Normalize and evaluate search results.
-   Score candidate matches.
-   Detect potential version mismatches.
-   Rank search results.
-   Apply a configurable result limit.

### Download engine

-   Sequential queue processing.
-   Configurable retries per provider.
-   Provider fallback.
-   Download eligibility checks.
-   Partial-file handling.
-   Cleanup of incomplete downloads.
-   Interruption handling.

### Persistent storage

-   SQLite database.
-   Persistent download history.
-   Duplicate-download prevention through historical records.
-   Queue replacement without destroying completed-download history.
-   Recovery of stale operations after interruptions.

### Command-line interface

The application uses Typer for command handling and Rich for terminal
output.

It provides commands for importing, reviewing, starting, pausing,
resuming, retrying, checking status, inspecting sources, managing
configuration, and viewing history.

------------------------------------------------------------------------

# 3. Provider Support

The application uses independent provider adapters rather than placing
all source-specific logic inside the download engine.

This makes it easier to add, modify, or disable integrations without
redesigning the entire application.

  ---------------------------------------------------------------------------
  Provider          Search            Download              Current status
  ----------------- ----------------- --------------------- -----------------
  Audius            Yes               Yes, when explicitly  Integrated
                                      permitted             

  Jamendo           Yes               Yes, when properly    Integrated;
                                      configured and        requires client
                                      permitted             ID

  FreeToUse         Yes               Restricted pending    Search adapter
                                      rights review         integrated

  ccMixter          Yes               Restricted pending    Search adapter
                                      rights review         integrated

  Internet Archive  Yes               Yes, for verified     Integrated
                                      permissive-licensed   
                                      originals             

  Direct URL        Not automatically Yes, for authorized   Integrated
                    searched          direct URLs           

  Tubidy            No automated      No automated download Placeholder
                    search                                  retained for
                                                            compatibility
  ---------------------------------------------------------------------------

## Audius

Audius is integrated as a search and download provider.

The adapter:

-   Searches for tracks.
-   Attempts a title-and-artist search.
-   Falls back to title-only search when necessary.
-   Handles malformed or incomplete search results.
-   Checks download eligibility.
-   Rejects results that do not satisfy the required rights conditions.

An Audius API key can be supplied through the `AUDIUS_API_KEY`
environment variable.

The availability of individual tracks depends on the provider's response
and the applicable download permissions.

## Jamendo

Jamendo is integrated as a search and download provider.

It requires a valid client ID.

The application supports multiple Jamendo client IDs, allowing
credential rotation where configured.

Supported configuration sources include:

-   `JAMENDO_CLIENT_IDS`
-   `JAMENDO_CLIENT_ID`
-   `jamendo_client_ids` in the configuration file
-   `jamendo_client_id` in the configuration file

A valid client ID is required before Jamendo search functionality can be
used.

## FreeToUse

FreeToUse is integrated as a search adapter.

Search results require rights review before they can be considered
eligible for automatic downloading.

The application deliberately does not treat every search result as
downloadable content.

## ccMixter

ccMixter is integrated as a Creative Commons-oriented search adapter.

Its results are subject to rights verification.

Automatic downloads are restricted while a result requires manual rights
review.

## Internet Archive

Internet Archive provides a public metadata and audio-download
integration.

The adapter:

-   Searches archive metadata.
-   Supports title-and-artist searches.
-   Falls back to title-only searches.
-   Filters for suitable audio media.
-   Evaluates licensing and rights information.
-   Rechecks metadata before downloading.
-   Rejects restricted or unverified content.
-   Downloads eligible original audio files.

Internet Archive can contain recordings that are not the requested
studio version, including covers, live performances, and unrelated
audio.

A successful search is not proof that a result is the correct track.

## Direct URL

The Direct URL provider supports explicitly supplied, authorized HTTPS
audio URLs.

It is not automatically searched by the global search engine.

The current importer does not provide a complete URL-column workflow, so
attaching direct URLs to tracks remains a more advanced/manual workflow.

## Tubidy

Tubidy is retained as a compatibility placeholder.

I have deliberately not implemented automated scraping, DRM
circumvention, or access-control bypassing.

I will only consider an integration if a permitted and technically
stable access method is available.

------------------------------------------------------------------------

# 4. How the Application Works

The application follows a pipeline that separates importing, searching,
matching, eligibility checks, downloading, and persistence.

``` text
                 MUSIC LIST
                     |
                     v
              IMPORTER
                     |
                     v
              ACTIVE QUEUE
                     |
                     v
              SEARCH ENGINE
                     |
          +----------+----------+
          |          |          |
          v          v          v
        Audius    Jamendo    Other sources
          |          |          |
          +----------+----------+
                     |
                     v
              MATCH EVALUATION
                     |
                     v
             RIGHTS / VERSION CHECK
                     |
              +------+------+
              |             |
              v             v
          Eligible       Ineligible
              |             |
              v             v
         DOWNLOAD       REJECT / REVIEW
              |
              v
        FILE VALIDATION
              |
        +-----+------+
        |            |
        v            v
     Success       Failure
        |            |
        v            v
    DATABASE      RETRY / FALLBACK
        |
        v
  DOWNLOAD HISTORY
```

The main components have distinct responsibilities:

  -----------------------------------------------------------------------
  Component                           Responsibility
  ----------------------------------- -----------------------------------
  Importer                            Reads TXT and CSV track lists

  Database                            Stores queue state and download
                                      history

  Providers                           Communicate with individual audio
                                      sources

  Search engine                       Collects, validates, ranks, and
                                      deduplicates candidates

  Matching logic                      Evaluates how closely a candidate
                                      matches the requested track

  Download engine                     Processes tracks sequentially and
                                      manages retries

  CLI                                 Exposes application functionality
                                      to the user
  -----------------------------------------------------------------------

SQLite is used for persistent application state.

------------------------------------------------------------------------

# 5. Requirements

The current project targets Ubuntu Linux.

Requirements:

-   Ubuntu Linux
-   Python 3.10 or newer
-   Internet connection
-   pip
-   Python virtual environment support

Python dependencies are managed through `pyproject.toml`.

Main dependencies:

-   Typer
-   Rich
-   HTTPX
-   Mutagen

Development dependency:

-   pytest

------------------------------------------------------------------------

# 6. Installation

## Step 1: Install system dependencies

``` bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip git unzip
```

## Step 2: Obtain the project

Clone the repository:

``` bash
git clone <REPOSITORY_URL>
```

Enter the project directory:

``` bash
cd bulk-music-downloader
```

Alternatively, extract the downloaded project archive and enter its
directory.

## Step 3: Create a virtual environment

``` bash
python3 -m venv .venv
```

Activate it:

``` bash
source .venv/bin/activate
```

## Step 4: Install the application

``` bash
python -m pip install --upgrade pip
python -m pip install -e .
```

## Step 5: Verify installation

``` bash
music-batch --help
```

If installation succeeded, the CLI help page should display the
available commands.

## Step 6: Optional development installation

If you want to run the project's test suite:

``` bash
python -m pip install -e ".[dev]"
```

Run:

``` bash
pytest -q
```

------------------------------------------------------------------------

# 7. Configuration

The application stores its configuration in:

``` text
~/.config/bulk-music-downloader/config.toml
```

The configuration directory is created automatically.

## Default configuration

The initial configuration includes:

  -----------------------------------------------------------------------
  Setting                             Default
  ----------------------------------- -----------------------------------
  Download directory                  `~/Music/BulkDownloads`

  Providers                           Audius, Jamendo, FreeToUse,
                                      ccMixter, Internet Archive, Direct
                                      URL

  Retries per provider                3

  Request timeout                     30 seconds

  Maximum search results              8

  Jamendo client ID                   Empty

  Audius API key                      Empty
  -----------------------------------------------------------------------

## Inspect configuration

``` bash
music-batch config-show
```

## Change configuration

The general command format is:

``` bash
music-batch config-set KEY VALUE
```

Examples:

``` bash
music-batch config-set download_dir '~/Music/BulkDownloads'
music-batch config-set retries_per_provider 3
music-batch config-set request_timeout 30
music-batch config-set providers 'audius,jamendo,internet_archive,direct_url'
```

Provider names must be valid.

## Jamendo credentials

Set a single client ID:

``` bash
export JAMENDO_CLIENT_ID="YOUR_CLIENT_ID"
```

Or multiple client IDs:

``` bash
export JAMENDO_CLIENT_IDS="CLIENT_ID_1,CLIENT_ID_2"
```

## Audius credentials

``` bash
export AUDIUS_API_KEY="YOUR_API_KEY"
```

Environment variables take precedence over the corresponding
configuration-file credentials.

Do not commit API credentials, access tokens, or private configuration
files to Git.

------------------------------------------------------------------------

# 8. Preparing a Music Queue

The application supports TXT and CSV imports.

## TXT format

Create a file called `songs.txt`:

``` text
Blinding Lights | The Weeknd
Believer | Imagine Dragons
Counting Stars | OneRepublic
Numb | Linkin Park
```

Supported TXT formats:

``` text
Title | Artist
Title - Artist
Title<TAB>Artist
```

Each line represents one track.

## CSV format

CSV files should contain columns named:

``` csv
title,artist
Blinding Lights,The Weeknd
Believer,Imagine Dragons
Counting Stars,OneRepublic
```

Column names are case-insensitive.

## Import the list

``` bash
music-batch import songs.txt
```

Or:

``` bash
music-batch import songs.csv
```

### Important: Queue replacement

Importing a new list replaces the active queue.

It does not simply append new tracks to the existing active queue.

However, historical download records are preserved independently.

This is intentional. I want users to be able to work with different
music lists without losing their previous download history or
unnecessarily downloading tracks again.

------------------------------------------------------------------------

# 9. Using the Application

A typical workflow looks like this.

## Step 1: Import tracks

``` bash
music-batch import songs.txt
```

## Step 2: Review the queue

``` bash
music-batch review
```

## Step 3: Inspect available sources

``` bash
music-batch sources
```

## Step 4: Start downloading

``` bash
music-batch start
```

The engine processes tracks sequentially.

It searches configured providers, evaluates candidates, applies
eligibility checks, and attempts to download suitable results.

## Step 5: Check progress

``` bash
music-batch status
```

## Step 6: Review download attempts

``` bash
music-batch history
```

## Step 7: Retry failed tracks

``` bash
music-batch retry-failed
```

The application maintains its database state between operations.

------------------------------------------------------------------------

# 10. Command Reference

  Command                              Description
  ------------------------------------ ----------------------------------------
  `music-batch`                        Opens the interactive application menu
  `music-batch --help`                 Displays CLI help
  `music-batch import FILE`            Imports a TXT or CSV list
  `music-batch review`                 Reviews the active queue
  `music-batch start`                  Starts or continues queue processing
  `music-batch pause`                  Requests a cooperative pause
  `music-batch resume`                 Clears the pause request
  `music-batch retry-failed`           Requeues failed tracks
  `music-batch status`                 Displays queue totals
  `music-batch sources`                Displays configured providers
  `music-batch config-show`            Displays current configuration
  `music-batch config-set KEY VALUE`   Updates a configuration setting
  `music-batch history`                Displays recent download attempts

## Pause behavior

Pause is cooperative.

If a download is already in progress, the engine allows the current
operation to finish or reach its timeout before stopping at a track
boundary.

It does not forcibly terminate an active HTTP transfer.

## Interruption behavior

The application handles Ctrl+C during queue processing.

The current operation is marked interrupted, incomplete files are
cleaned up, and processing stops.

On a subsequent run, stale searching or downloading states can be
recovered rather than remaining permanently stuck.

------------------------------------------------------------------------

# 11. Queue and Download Management

A central design decision in this project is the separation of the
active queue from persistent download history.

I do not want importing a new music list to destroy information about
previous downloads.

The database therefore maintains separate records for:

-   Active queue entries
-   Historical download records
-   Download attempts and statuses

## Track states

The engine uses statuses including:

  Status          Meaning
  --------------- ----------------------------------------------
  `pending`       Waiting to be processed
  `searching`     Searching providers
  `downloading`   A download is in progress
  `completed`     Download completed successfully
  `failed`        Processing failed
  `skipped`       No acceptable candidate met the requirements
  `interrupted`   Processing was interrupted

## Duplicate prevention

When a track is successfully completed, its download is recorded in
persistent history.

When a new queue is imported, the application preserves that history.

This helps prevent previously downloaded tracks from being downloaded
again unnecessarily.

## Provider fallback

If one provider fails to produce a usable result or cannot complete a
download, the engine can try another configured provider.

Each provider receives the configured number of retries.

The default is three attempts per provider.

A failed provider should not automatically stop the entire batch.

------------------------------------------------------------------------

# 12. Data Storage and Recovery

The application follows the standard Linux user-directory layout.

  -----------------------------------------------------------------------------------------
  Data                                Location
  ----------------------------------- -----------------------------------------------------
  Configuration                       `~/.config/bulk-music-downloader/config.toml`

  SQLite database                     `~/.local/share/bulk-music-downloader/downloads.db`

  Application logs                    `~/.local/state/bulk-music-downloader/app.log`

  Downloaded audio                    `~/Music/BulkDownloads`
  -----------------------------------------------------------------------------------------

The download directory can be changed through configuration.

## Database persistence

Queue state and download history are stored in SQLite.

The database is independent of the replaceable imported queue.

This allows the application to retain completed-download information
when users import new lists.

## Download safety

Downloads use temporary `.part` files.

A temporary file is only promoted to its final destination after the
download passes the applicable validation checks.

Incomplete files are cleaned up when a download fails or is interrupted.

## Backup recommendation

The SQLite database contains important application state.

Back it up before performing manual database operations or making
significant changes to the application.

For example:

``` bash
mkdir -p ~/bulk-music-downloader-backup
cp ~/.local/share/bulk-music-downloader/downloads.db \
   ~/bulk-music-downloader-backup/
```

Do not delete or reset the database merely to clear the active queue.

Use the application's import and queue-management functionality instead.

------------------------------------------------------------------------

# 13. Matching and Download Safety

A major challenge in bulk music downloading is finding the correct
recording.

A search for a song can return:

-   The requested studio recording
-   A live recording
-   A remix
-   A cover
-   An instrumental version
-   A different artist's recording
-   An unrelated audio file

The application therefore evaluates candidates rather than blindly
downloading the first search result.

## Matching

The search system considers track information and candidate quality.

It supports:

-   Title-and-artist searches
-   Title-only fallback where supported
-   Candidate normalization
-   Duplicate candidate removal
-   Match scoring
-   Version mismatch detection
-   Candidate ranking

The download engine applies a configurable minimum match threshold.

A candidate below the required threshold may be skipped.

## Rights verification

I deliberately use strict eligibility checks.

A result must satisfy the following conditions before automatic
downloading:

-   Its rights status must be explicitly permitted.
-   Its provider must explicitly allow downloading.
-   It must not be identified as a version mismatch.

In simplified form:

``` python
return (
    result.rights_status == "permitted"
    and result.download_allowed is True
    and result.version_match is not False
)
```

Results requiring rights review are not automatically treated as
permitted downloads.

I do not intend to weaken these checks simply to increase the number of
completed downloads.

**A high download count is not worth compromising licensing
safeguards.**

Users remain responsible for checking the applicable licensing terms and
ensuring their intended use is authorized.

This project does not implement DRM circumvention, access-control
bypassing, or unauthorized streaming extraction.

------------------------------------------------------------------------

# 14. Testing and Validation

I use automated tests to validate the application's core functionality.

The v0.1.0 release validation includes:

-   Python compilation checks.
-   Provider integration tests.
-   Audius search fallback tests.
-   Internet Archive search and download tests.
-   Jamendo credential rotation tests.
-   Direct URL provider tests.
-   Matching and search tests.
-   Queue replacement tests.
-   Persistent download-history tests.
-   Download-engine tests.
-   Failure and interruption handling tests.

## Run the tests

Install development dependencies:

``` bash
python -m pip install -e ".[dev]"
```

Run the complete suite:

``` bash
pytest -q
```

## v0.1.0 validation result

``` text
100 passed
```

Python compilation validation:

``` bash
python -m compileall -q src tests
```

The v0.1.0 release passed both checks on my Ubuntu development
environment.

### Important distinction

Passing automated tests demonstrates that the tested application logic
works under the test conditions.

It does not guarantee that every external provider is always available
or that every requested song can be downloaded.

Live provider reliability and successful real-world matching remain
areas for further testing.

------------------------------------------------------------------------

# 15. Development Progress

This section records what I have achieved and what I consider
unfinished.

## Completed in v0.1.0

  Area                   Achievement
  ---------------------- ------------------------------------------------
  Project foundation     Python package and installable CLI
  CLI                    Typer-based command interface
  Terminal output        Rich integration
  Importer               TXT and CSV support
  Queue management       Active queue replacement
  Database               SQLite persistence
  Download history       Separate persistent history
  Duplicate prevention   Historical completion tracking
  Search architecture    Multi-provider search system
  Matching               Candidate scoring and ranking
  Audius                 Search and download integration
  Jamendo                Search and download integration
  FreeToUse              Search adapter with rights-review restrictions
  ccMixter               Search adapter with rights-review restrictions
  Internet Archive       Search and download integration
  Direct URL             Authorized HTTPS direct-download adapter
  Tubidy                 Safe placeholder retained
  Download engine        Sequential processing
  Reliability            Retry and provider fallback
  Recovery               Interrupted-operation recovery
  File handling          Partial-download cleanup
  Configuration          TOML configuration and environment overrides
  Testing                100 passing automated tests
  Release                Git commit and annotated `v0.1.0` tag

## Partially completed

  -----------------------------------------------------------------------
  Area                    Current state           Remaining work
  ----------------------- ----------------------- -----------------------
  Audius                  Integrated              More live provider
                                                  testing

  Jamendo                 Integrated              Configure valid
                                                  credentials and verify
                                                  live downloads

  FreeToUse               Search integration      Complete
                                                  rights-verification
                                                  workflow

  ccMixter                Search integration      Complete
                                                  rights-verification
                                                  workflow

  Internet Archive        Integrated              Improve real-world
                                                  match quality

  Direct URL              Download adapter        Better URL import and
                                                  management

  Matching                Scoring and version     Improve precision using
                          checks                  real-world results

  Queue management        Core operations         Additional usability
                          implemented             improvements

  Provider reliability    Retry and fallback      More live failure
                          implemented             testing

  User experience         CLI available           Better interaction and
                                                  progress reporting
  -----------------------------------------------------------------------

## Not yet achieved

The following should not be considered completed features in v0.1.0:

-   Fully reliable downloads across all providers.
-   Guaranteed matching of requested studio versions.
-   Automated rights verification for every provider.
-   A complete Direct URL import workflow.
-   Automated Tubidy integration.
-   Audio format conversion.
-   A graphical user interface.
-   A dedicated desktop or mobile application.
-   Production-grade monitoring and analytics.
-   A formal public contribution and release process.

------------------------------------------------------------------------

# 16. What I Still Want to Build

Version 0.1.0 establishes the foundation. I do not consider the project
finished.

My next development priorities are organized below.

## Phase 1 --- Provider reliability

**Objective:** Make existing integrations dependable in real-world use.

Planned work:

-   Configure and test Jamendo credentials.
-   Perform more live Audius searches and downloads.
-   Improve provider error classification.
-   Improve handling of rate limits and temporary outages.
-   Test provider fallback with real network failures.
-   Improve provider availability reporting.
-   Investigate why eligible results are sometimes unavailable.

## Phase 2 --- Rights and matching improvements

**Objective:** Improve result quality without weakening download
safeguards.

Planned work:

-   Improve title and artist matching.
-   Improve remix, live, cover, and studio-version detection.
-   Improve candidate explanations.
-   Build a clearer manual rights-review workflow.
-   Add more detailed provider-specific rights checks.
-   Reduce false-positive matches.

## Phase 3 --- Import and queue improvements

**Objective:** Make large music lists easier to manage.

Planned work:

-   Add a more convenient direct-URL import workflow.
-   Improve import validation and reporting.
-   Improve queue filtering and selection.
-   Improve duplicate detection.
-   Improve queue statistics.
-   Expand recovery and backup capabilities.

## Phase 4 --- Audio management

**Objective:** Extend the application beyond basic downloading.

Potential features:

-   Audio metadata inspection.
-   Better filename organization.
-   Optional audio format conversion.
-   Download-directory organization.
-   Improved duplicate-file detection.
-   Audio library reports.

These features will be developed only when the underlying download
workflow is sufficiently reliable.

## Phase 5 --- User experience

**Objective:** Make the application easier to operate.

Potential features:

-   Better live progress reporting.
-   More detailed download logs.
-   Improved interactive queue management.
-   Desktop interface.
-   Configuration management improvements.

## Phase 6 --- Long-term direction

The longer-term goal is to turn Bulk Music Downloader into a
well-structured audio acquisition and management application.

I want its architecture to remain modular so that new providers, storage
options, and user interfaces can be introduced without rewriting the
core engine.

These are development intentions, not promises that the features already
exist.

------------------------------------------------------------------------

# 17. Known Limitations

The following limitations apply to the current release.

1.  **Provider availability:** External providers can change their APIs,
    impose limits, or become unavailable.

2.  **Jamendo configuration:** A valid client ID is required. The
    default configuration does not include one.

3.  **Audius configuration:** An API key can be supplied through the
    environment. Live endpoint availability and download permissions
    still determine what works.

4.  **Rights-review providers:** FreeToUse and ccMixter results are not
    automatically downloadable while they require rights review.

5.  **Internet Archive results:** Search results may contain recordings
    that do not match the requested studio version.

6.  **Direct URLs:** The provider is integrated, but the ordinary
    TXT/CSV importer does not yet offer a complete URL-import workflow.

7.  **Tubidy:** No automated integration is implemented.

8.  **Matching accuracy:** Search scores are estimates, not guarantees
    of musical identity.

9.  **No transcoding:** The application does not currently provide a
    complete audio-conversion workflow.

10. **CLI only:** The current release does not include a graphical
    interface.

11. **Live acceptance:** Automated tests pass, but broader real-world
    provider testing remains necessary.

12. **Platform coverage:** Ubuntu is the primary development target.
    Other operating systems have not been established as supported
    platforms.

------------------------------------------------------------------------

# 18. Troubleshooting

## `music-batch: command not found`

Ensure the virtual environment is activated:

``` bash
source .venv/bin/activate
```

If the command is still unavailable:

``` bash
python -m pip install -e .
```

## No Jamendo results

Check whether a valid client ID is configured:

``` bash
music-batch config-show
```

Set the environment variable:

``` bash
export JAMENDO_CLIENT_ID="YOUR_CLIENT_ID"
```

## No eligible download candidates

This does not necessarily mean the application is broken.

Possible causes include:

-   No matching track was found.
-   The provider returned a different version.
-   The candidate did not meet the match threshold.
-   The provider did not explicitly permit downloading.
-   Rights information was missing or uncertain.
-   The source was temporarily unavailable.

Do not disable rights checks simply to force a download.

## Downloads are failing

Check:

-   Internet connectivity.
-   Provider availability.
-   API credentials.
-   Request timeout configuration.
-   Application logs.

Log location:

``` text
~/.local/state/bulk-music-downloader/app.log
```

## Interrupted tracks

The engine can recover stale searching and downloading states during a
subsequent queue run.

Check the queue:

``` bash
music-batch review
```

Check totals:

``` bash
music-batch status
```

## Failed tracks

Retry failed tracks:

``` bash
music-batch retry-failed
```

------------------------------------------------------------------------

# 19. Project Structure

The project follows a Python `src` layout.

``` text
bulk-music-downloader/
│
├── examples/
│   └── songs.txt
│
├── src/
│   └── bulk_music_downloader/
│       │
│       ├── providers/
│       │   ├── __init__.py
│       │   ├── audius.py
│       │   ├── jamendo.py
│       │   ├── freetouse.py
│       │   ├── ccmixter.py
│       │   ├── internet_archive.py
│       │   ├── direct_url.py
│       │   └── tubidy.py
│       │
│       ├── __init__.py
│       ├── config.py
│       ├── database.py
│       ├── engine.py
│       ├── importer.py
│       ├── main.py
│       ├── matching.py
│       ├── models.py
│       └── search.py
│
├── tests/
│   ├── test_direct_url.py
│   ├── test_engine.py
│   ├── test_importer.py
│   ├── test_internet_archive.py
│   ├── test_jamendo_rotation.py
│   ├── test_matching.py
│   ├── test_new_providers.py
│   ├── test_phase_23_providers.py
│   ├── test_queue_replacement.py
│   └── test_search.py
│
├── .gitignore
├── pyproject.toml
└── README.md
```

------------------------------------------------------------------------

# 20. Developer

**Built and maintained by Derrick.**

Bulk Music Downloader is an independent software project I am developing
to explore practical Python application engineering, API integrations,
database-backed queue management, search systems, and reliable file
downloads.

I built the first release around a simple principle:

> A useful downloader should do more than download files. It should
> manage the entire process responsibly, preserve its state, handle
> failure, and make its behavior understandable.

Version `0.1.0` is the foundation.

There is still considerable work ahead, particularly around live
provider reliability, matching accuracy, and rights verification.

I intend to keep improving the project incrementally, with reliability
and maintainability taking priority over adding features for the sake of
adding features.

**--- Derrick**

------------------------------------------------------------------------

*Bulk Music Downloader v0.1.0 --- Initial multi-source release.*
