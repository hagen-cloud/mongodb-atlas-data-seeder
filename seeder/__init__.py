"""MongoDB Atlas data seeder.

A multi-process / multi-threaded tool that populates a MongoDB Atlas cluster
with mock data generated from JSON templates, until a configurable storage
target (e.g. 4TB) is reached. Designed to run as a parallel (indexed) Job on
Kubernetes, with local Python and Docker execution also supported.
"""

__version__ = "0.1.0"
