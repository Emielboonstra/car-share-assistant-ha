# Car share assistant service-API v1

Contract voor app-versie 0.3.0. Deze endpoints zijn geïmplementeerd in de eigen Car share assistant-server en met een tijdelijke testdatabase getest. Voorbeelden bevatten fictieve gegevens. De webapp is een apart project; deze repository bevat het contract voor de toekomstige HA-client.

## Authenticatie en bevoegdheden

Home Assistant meldt eenmalig aan met een beheerdersgebruikersnaam en wachtwoord via `POST /api/v1/auth/login`. Invoer: `username`, `password` en optioneel `name` (standaard Home Assistant). Antwoord HTTP 201: `token`, `key_id`, `instance_id`, `api_version`. Deze route vereist `X-Carshare-Request: 1`, heeft dezelfde inloglimiet als de webaanmelding, weigert gewone gezinsaccounts en zet geen webcookie. HA bewaart de servicecredential en niet het wachtwoord. `DELETE /api/v1/auth/key` met Bearer-auth trekt uitsluitend de eigen credential in. Een beheerder kan daarnaast in **Instellingen → Home Assistant** een sleutel aanmaken of intrekken. De volledige sleutel verschijnt één keer. De server bewaart alleen een SHA-256-hash. De sleutel heeft geen automatische vervaldatum, kan worden ingetrokken en blijft onafhankelijk van websessies geldig. Intrekken werkt vanaf het eerstvolgende verzoek. Als de eigenaar geen beheerder meer is, werkt de sleutel niet meer.

Alle verzoeken sturen `Authorization: Bearer <API-sleutel>`. Schrijfverzoeken sturen daarnaast `X-Carshare-Request: 1` en JSON `Content-Type: application/json`. Cookies en CSRF-tokens zijn voor deze service-endpoints niet nodig. Gebruik bij voorkeur HTTPS; controleer certificaten en stuur sleutels nooit in URL’s, logs of naar een andere host na een redirect.

Elke sleutel mag gezinsleden, auto’s, tarieven, planning en kosten lezen. Optioneel mag de sleutel reserveringen voor **ieder gezinslid** aanmaken, aanpassen en annuleren. Dit is een gezinsbrede servicebevoegdheid, geen aanmelding als die persoon. Auditregels vermelden de service-ID; de geselecteerde persoon is de bestuurder. De sleutel geeft geen toegang tot wachtwoorden, websessies, activiteiten, gebruikersbeheer, autobeheer of tariefwijzigingen. Webgebruikers behouden hun eigen rechten.

## Endpoints

Alle paden zijn relatief aan het app-adres. Alle antwoorden zijn JSON en `Cache-Control: no-store`.

| Methode en pad | Invoer | Antwoord |
| --- | --- | --- |
| `GET /api/v1/info` | Geen | API/app-versie, stabiele `instance_id`, tijdzone, valuta, mogelijkheden en daadwerkelijke `permissions` van de sleutel |
| `GET /api/v1/state` | Geen | `people`, `vehicles`, actuele `rates`; geen reserveringen |
| `GET /api/v1/reservations` | Verplicht `start`, `end`; optioneel `vehicle_id`, `person_id`, `include_cancelled=false`, `offset=0`, `limit=200` | `reservations`, `next_offset` of null, `total` |
| `GET /api/v1/reservations/{id}` | Reserverings-ID | Eén reservering, ook na annulering |
| `POST /api/v1/reservations` | Volledig reserveringsobject plus header `Idempotency-Key` | HTTP 201; `reservation` en `replayed` |
| `PUT /api/v1/reservations/{id}` | Volledig reserveringsobject met actueel `version` | `reservation` |
| `DELETE /api/v1/reservations/{id}` | Queryparameter `version` verplicht | `reservation` met status `cancelled` |
| `GET /api/v1/availability` | `vehicle_id`, `start`, `end`; optioneel `exclude_reservation_id` | `available`, `conflicting_reservation_ids` |
| `GET /api/v1/costs` | `month=YYYY-MM` verplicht | `month`, `currency=EUR`, `includes_planned_reservations=true`, `people` |

Tijdsfilters gebruiken ISO 8601 met offset of `Z`. Het bereik is halfopen `[start, end)` en maximaal 366 dagen per verzoek. Reserveringen die het bereik overlappen worden opgenomen. `person_id` filtert op deelname, inclusief bestuurder. Paginering: `limit` 1–500; volg `next_offset` tot null. Sorteervolgorde is datum, begintijd, ID. Er is geen vast venster van 14 dagen; vraag kalenderperioden naar behoefte op. Bij wijzigingen tussen pagina’s kan een client een nieuwe reeks ophalen en op ID dedupliceren.

## Modellen

`people`: `id`, `name`, `username`, `role` (`admin`/`member`), `color`, `version`.

`vehicles`: `id`, `name`, `plate`, `detail`, `version`.

`rates`: `zName`, `gName` (aanpasbare bestemmingen), `z`, `g` (prijs per retour), `km` (prijs per kilometer).

Reserveringsinvoer:

```json
{
  "vehicle_id": "example-car",
  "person_id": "example-person-a",
  "start_time": "2026-12-12T09:00:00+01:00",
  "end_time": "2026-12-12T17:00:00+01:00",
  "route": "g1",
  "participants": ["example-person-b"],
  "kilometers": 0,
  "comment": "Samen naar een afspraak"
}
```

Verplicht: auto, bestuurder, start/eind en route. `participants` standaard leeg; de bestuurder wordt altijd toegevoegd en deelnemers worden gededupliceerd. Iedereen moet in het gezin bestaan. `comment` standaard leeg, maximaal 2000 tekens. `kilometers` standaard 0, maximaal 100000, één decimaal; bij `other` verplicht groter dan nul. Bij wijzigen is `version` verplicht voor de gelijktijdigheidscontrole. Het is een volledige vervanging, dus stuur alle gewenste gegevens opnieuw.

Routes: `z1` één retour naar bestemming z, `z2` twee retours, `g1` één retour naar bestemming g, `other` losse kilometers. Namen komen uit de instellingen. Alle webappopties zijn beschikbaar via de API.

Start/eind worden naar `Europe/Amsterdam` omgerekend. Beide moeten op dezelfde lokale dag en op hele minuten vallen; begin ligt voor einde. Niet-bestaande en dubbelzinnige lokale tijden rond zomertijd/wintertijd worden geweigerd. Het systeem ondersteunt momenteel geen ritten over middernacht. Reserveren in het verleden is, net als in de webapp, toegestaan.

Reserveringsantwoord bevat `id`, `vehicle_id`, `vehicle_name`, `person_id`, `person_name`, `start_time`, `end_time` met juiste lokale offset, `route`, `participants` inclusief bestuurder, `kilometers`, `comment`, opgeslagen `rates`, `total_cents`, `shares`, `status` (`active`/`cancelled`) en `version`.

`shares` bevat per deelnemer `person_id` en `amount_cents`. Geldbedragen zijn gehele eurocenten. Tarieven worden bij aanmaken opgeslagen en blijven bij wijzigingen behouden. Het bedrag wordt gelijk verdeeld; resterende centen gaan in volgorde eerst naar de bestuurder, daarna de overige deelnemers.

Maandkosten bevatten per persoon `person_id`, `name`, `amount_cents`, `through_today_cents`, `reservation_count`, `driver_count`. Dit zijn reserveringskosten, inclusief geplande ritten; geen bewijs van daadwerkelijk gereden kilometers of betalingen. `through_today_cents` telt reserveringen op datums tot en met vandaag, Amsterdamse tijd. Geannuleerde ritten tellen niet mee.

## Conflicten, retries en fouten

De server controleert overlap binnen een schrijftransactie. Beschikbaarheidscontrole is een momentopname en blokkeert de auto niet. Aansluitende ritten zijn toegestaan. Aanmaken vereist een per logische actie unieke `Idempotency-Key` van 16–80 letters/cijfers/koppeltekens. Bewaar dezelfde sleutel en dezelfde invoer bij het herstellen van een onzekere netwerkuitkomst. Een herhaald verzoek met dezelfde sleutel maakt geen tweede rit. Gebruik die sleutel nooit voor een andere rit of gewijzigde invoer. Sleutels worden per API-credential gescheiden.

`PUT` en `DELETE` vereisen het actuele versienummer. Na een timeout eerst `GET` uitvoeren om de feitelijke toestand vast te stellen; niet blind opnieuw muteren. Annuleren bewaart het record met verhoogde versie. Een tweede annulering antwoordt 404 omdat er geen actieve rit meer is. Een replay van een eerdere aanmaak kan het inmiddels geannuleerde record teruggeven; dat maakt de annulering niet ongedaan.

Fouten hebben `{"detail":"menselijk leesbare fout"}`. Momenteel zijn er geen afzonderlijke machinecodes; gebruik status en bewerkingscontext, geen tekstherkenning.

| Status | Betekenis |
| --- | --- |
| 401 | Ontbrekende/ongeldige/ingetrokken sleutel |
| 403 | Sleutel heeft geen schrijfrecht, verkeerde requestheader of vreemde Origin |
| 404 | Auto/reservering niet gevonden, of geen actieve rit meer bij wijzigen/annuleren |
| 409 | Overlap, verouderde versie of hergebruik van idempotentiesleutel voor andere invoer |
| 413 | Schrijfverzoek groter dan 32 KiB volgens Content-Length |
| 422 | Ongeldige velden, tijden, deelnemers, kilometers, bereik of ontbrekende idempotentiesleutel |
| 5xx / timeout | Onzekere of tijdelijke server/netwerkfout; lees opnieuw voordat je een mutatie herhaalt |

Er is geen specifieke API-quota of pushverbinding. De HA-client moet redelijk pollen en gelijktijdige verversingen samenvoegen; voorstel elke vijf minuten en meteen na een eigen wijziging. Webinlogpogingen hebben apart een limiet van 15 per kwartier per bronadres.

## Python-clientontwerp

Een async `CarShareClient` ontvangt een bestaande `aiohttp.ClientSession`, een gevalideerd app-adres en de API-sleutel. Methoden: `async_get_info`, `async_get_state`, `async_get_reservations` (alle pagina’s), `async_get_reservation`, `async_get_costs`, `async_check_availability`, `async_create_reservation`, `async_update_reservation`, `async_cancel_reservation`.

Gebruik een begrensde timeout, certificaatcontrole, geen redirects naar andere hosts, geen credentiallogging en duidelijke exceptions voor authenticatie, bevoegdheden, conflicten, invoer en verbinding. Geen automatische herhaling van mutaties. De aanroepende actie houdt de idempotentiesleutel vast. Stabiele IDs combineren `instance_id` met auto/persoon-ID. De client en integratie staan in `custom_components/car_share_assistant`.

## Automatische ontdekking

De webapp kan met `CARSHARE_DISCOVERY=1` mDNS adverteren op `_carshare._tcp.local.`. TXT-velden bevatten alleen het stabiele `id`, `api=1` en optioneel het ingestelde HTTPS-`url`. Geen accounts of secrets. Zonder HTTPS-adres wordt het gevonden lokale adres met poort gebruikt. Een bestaande HA-configuratie wordt niet automatisch door mDNS aangepast; het adres kan via Opnieuw configureren worden gewijzigd na controle van het installatie-ID.
