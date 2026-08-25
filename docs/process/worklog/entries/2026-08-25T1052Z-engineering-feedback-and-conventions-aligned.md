# Engineering feedback and conventions aligned

RS-024 consolidated import-direction enforcement under the relative-aware
`tests/test_architecture.py` owner while retaining the credential-free agent
request contract in its host unit test. The architecture suite now protects
sibling isolation, neutral contracts, positive host composition, Petrus runtime
custody, provider-library ownership, and Petrus facade removal.

RS-028 adapted reusable Petrus boundary, durability, Activity, retry, testing,
and evidence practices to Hamsterdan without adopting Petrus's internal package
graph. `scripts/check` now runs frozen from the repository root, supports
path-scoped quick feedback, documents its profiles, and includes the architecture
contract. Orb setup tests run only on the GNU/Linux environment they specify.

Focused validation passed 16 tests. The default and path-scoped quick profiles
passed over 105 maintained Python files and 10 architecture checks. The routine
Python suite passed 1,100 tests with 17 intentional Orb platform skips on macOS;
the distribution build and all 9 Amp relay tests passed. TypeScript compilation
passed. The local demo-video run used Bun 1.4.0 rather than the required 1.3.10,
then passed 36 tests before one Playwright timeout closed the shared browser and
caused seven follow-on failures. The Navigator accepted that environment-qualified
evidence. Independent review findings were corrected before closure.
