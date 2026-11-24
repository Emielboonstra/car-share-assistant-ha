# Implementatieplan Home Assistant

Status: de eerste testversie 0.1.0 is geïmplementeerd. Onderstaande afspraken vormen de basis. De actuele installatie- en testinstructies staan in de README.

## Afgesproken basis

Eén config entry per Car share assistant-installatie, met automatisch ontdekt app-adres en een beheerdersaanmelding die een servicecredential oplevert. Het adres is later herconfigureerbaar; het wachtwoord wordt niet bewaard. Geen aparte websessie per gezinslid: de service mag voor alle gezinsleden reserveringen beheren. Config Flow test API-versie en sleutel; reauth vervangt ingetrokken sleutels. Het stabiele `instance_id` voorkomt dubbele installaties.

Eén apparaat per auto en één apparaat per persoon, met stabiele server-IDs. De autokalender is uitsluitend lezen: geen `async_create_event`, `async_update_event` of `async_delete_event`. Een afspraak toont bestuurder, begin/einde, deelnemers, route en opmerking. Kalenderopvragen gebruiken de werkelijk gevraagde periode, volgen paginering en verwerken tijdzones. Een persoonskalender is uitgesteld.

Persoonsensoren: kosten deze maand, vorige maand, kosten tot en met vandaag, aantal deelnames en bestuurdersritten deze maand, volgende reservering. Bedragen zijn aandelen in reserveringen, inclusief geplande ritten. Autosensoren: nu gereserveerd, huidige bestuurder, volgende reservering en start/einde. Bepaal actief zijn op actuele tijd; laat dat niet vijf minuten afhangen van netwerkpolling.

## Acties

Algemene acties onder het domein `car_share_assistant`:

| Actie | Gedrag |
| --- | --- |
| `create_reservation` | Auto, persoon, start, einde, route, deelnemers, kilometers, opmerking; resultaat ID en kostenverdeling |
| `update_reservation` | Geselecteerde reservering en alle gewenste velden; actuele versie controleren |
| `cancel_reservation` | Geselecteerde reservering annuleren met versiecontrole |
| `check_availability` | Beschikbaarheid voor auto en periode opvragen, zonder reserveren |
| `get_reservations` | Periode en optioneel auto/persoonfilter; geeft gestructureerde resultaten |
| `refresh` | Ververs relevante gegevens |

Alle HA-gebruikers die de acties mogen aanroepen kunnen een gezinslid kiezen. De integratie claimt niet dat dit gezinslid zelf ingelogd is. Persoonlijke snelacties kunnen later scripts zijn die dezelfde algemene actie met een vaste persoon aanroepen; geen dynamische registraties per gebruiker nodig.

## Bouwvolgorde en verificatie

1. Async getypeerde client voor API v1, gemockte tests voor rechten, fouten, paginering, tijdzones, versieconflicten en onzekere netwerkuitkomsten.
2. Config Flow, opties voor verversingsinterval, reauth, coordinator en correct unloaden. Gedeelde metadata en maandtotalen iedere vijf minuten, directe verversing na eigen wijzigingen. Kalenderbereiken los opvragen met kortdurende cache. Reserveringen op ID dedupliceren.
3. Apparaten, alleen-lezen autokalenders, persoonlijke kosten- en volgende-ritsensoren.
4. Acties met persoons-/autokeuze en volledige webappopties, begrijpelijke fouten en responsegegevens. Nooit automatisch aanmaken herhalen met een nieuwe idempotentiesleutel.
5. Nederlandse/Engelse teksten, documentatie, tests, hassfest en compatibiliteitscontrole met de actuele HA-versie.
6. Pas bij werkende en geteste integratie: geldig manifest, Marketplace/HACS-metadata en eerste release. Daarna via custom repository installeren en op een testomgeving controleren. Geen echte reserveringen in geautomatiseerde tests.

Bronnen: [kalenderentiteit](https://contributors.home-assistant.io/core/entities/calendar/), [acties](https://contributors.home-assistant.io/core/integrations/actions/), [custom repositories](https://www.home-assistant.io/integrations/marketplace/#custom-repositories). Controleer deze officiële documentatie opnieuw bij de bouw; dit document beschrijft het ontwerp.
