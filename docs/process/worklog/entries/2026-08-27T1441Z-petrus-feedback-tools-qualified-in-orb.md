# Petrus feedback tools qualified in the Hamsterdan orb

Hamsterdan's orb setup now installs Docker and Graphviz, enables and starts the
Docker socket and service, and gives the orb user access to the socket. Resume
checks restart Docker when necessary. The setup also tolerates the newer `gh`
configuration file while preserving the existing fail-closed credential
custody rules.

This closes the feedback gap discovered while qualifying Petrus's unified Net
document: a fresh Hamsterdan orb can now execute the adjacent Petrus checkout's
Graphviz and real PostgreSQL checks instead of reporting those dependencies as
unavailable.

The setup completed twice, in 26.97 seconds and 17.93 seconds, and the resume
script completed afterward. Docker reported server 20.10.24 with the overlay2
driver; Graphviz `dot` reported 2.43.0. The focused Petrus PostgreSQL schema
test passed against a real container (`1 passed in 8.94s`). Shell syntax and
the final whitespace check also passed.
