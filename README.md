# Car share assistant voor Home Assistant

![Car share assistant](custom_components/car_share_assistant/brand/icon.png)

Custom integratie voor de eigen Car share assistant-webapp voor gezinsauto’s. **Testversie: 0.2.0.** Er is geen verbinding met Wheelshare.

Versie 0.2.0 ondersteunt meerdaagse reserveringen. Een beheerder kan in de webapp bij een persoon **Hoeft niet te betalen** inschakelen: zodra die persoon als bestuurder of medereiziger deelneemt, is de hele reservering voor iedereen gratis. Dat geldt ook voor bestaande reserveringen en wordt verwerkt in de HA-kostensensoren. Werk de integratie bij via Marketplace en herstart Home Assistant.

## Vereisten

- Home Assistant **2026.11.2 of hoger**.
- Car share assistant-webapp **0.4.0 of hoger**, bereikbaar vanaf Home Assistant.
- Een beheerdersaccount van de webapp. Een gewoon gezinsaccount mag geen HA-koppeling autoriseren.

## Installeren via Marketplace

1. Ga naar **Instellingen → Marketplace → Toevoegen via link**.
2. Voeg `https://github.com/Emielboonstra/car-share-assistant-ha` toe als **Integratie**.
3. Open de repository en installeer de integratie. Herstart Home Assistant wanneer daarom wordt gevraagd.
4. Ga naar **Instellingen → Apparaten & diensten** en configureer de ontdekte **Car share assistant**. Je kunt de integratie ook via **Integratie toevoegen** zoeken.
5. Log in met de gebruikersnaam en het wachtwoord van een Car share assistant-beheerder.

Het app-adres wordt automatisch via mDNS/Zeroconf gevonden; je hoeft het normaal niet in te voeren. De gevonden bestemming wordt getoond voordat je inlogt. De webapp kan zijn ingestelde HTTPS-adres bekendmaken; anders wordt het lokale HTTP-adres gebruikt. Home Assistant en de app moeten elkaar voor ontdekking op het lokale netwerk kunnen bereiken. Bij geblokkeerde multicast/VLAN’s kun je handmatig verbinden met het volledige app-adres, inclusief poort wanneer nodig.

Deze repository wordt als custom repository geïnstalleerd en is niet automatisch onderdeel van de publieke catalogus. Zie de [officiële Marketplace-uitleg](https://www.home-assistant.io/integrations/marketplace/#custom-repositories).

## Aanmelding en adres wijzigen

Je wachtwoord wordt uitsluitend bij het aanmelden verstuurd. De integratie bewaart een aparte, intrekbare servicecredential in de Home Assistant-config entry en bewaart het wachtwoord niet. Je hoeft geen API-sleutel te kopiëren. In de webapp zie je de koppeling bij **Instellingen → Home Assistant**, inclusief het laatste gebruik. Je kunt hem daar intrekken.

Bij een ingetrokken koppeling vraagt HA opnieuw om een beheerdersaanmelding. Het verwijderen van de integratie probeert de bijbehorende sleutel in te trekken; als de app offline is, kun je dat later in de webapp doen.

Het serveradres kun je later wijzigen via het menu van de integratie → **Opnieuw configureren**. Het nieuwe adres moet bij dezelfde installatie horen, zodat bestaande apparaten en entiteiten behouden blijven. Er worden nooit adressen of familiegegevens hardcoded in de integratie opgenomen. Automatische ontdekking wijzigt een bestaande verbinding niet ongemerkt.

## Apparaten en entiteiten

Voor iedere auto verschijnt één apparaat met:

- Een **uitsluitend leesbare kalender**. De titel is de bestuurder; begin/einde, deelnemers, auto, route en opmerking komen uit de reservering.
- Een binaire sensor **Gereserveerd** voor het huidige tijdstip.
- Sensoren voor **Huidige bestuurder**, **Volgende reservering begint** en **Volgende reservering eindigt**.

Voor ieder gezinslid verschijnt één apparaat met:

- **Kosten deze maand**, **Kosten vorige maand** en **Kosten tot en met vandaag**, in euro’s en op basis van het eigen aandeel.
- **Ritten deze maand**, **Bestuurdersritten deze maand** en **Volgende reservering**.

Kosten zijn reserveringskosten, inclusief geplande ritten, geen gemeten verbruik of betaalstatus. Gedeelde ritten worden gelijk verdeeld zoals in de webapp. De volgende reservering wordt als status tot één jaar vooruit gezocht; de kalender zelf vraagt de daadwerkelijk geopende periode op, ook daarbuiten. Een persoonlijke kalender is nog niet toegevoegd.

Auto- en persoonsnamen mogen wijzigen: unieke identiteit is gebaseerd op installatie-ID en het stabiele app-ID. Nieuw toegevoegde personen en auto’s worden bij het verversen ontdekt. Verwijderde objecten worden niet stilzwijgend uit de HA-registry gewist; hun entiteiten worden onbeschikbaar.

## Acties

| Actie | Functie |
| --- | --- |
| `car_share_assistant.create_reservation` | Reservering aanmaken voor een gekozen gezinslid |
| `car_share_assistant.update_reservation` | Alle gegevens van een reservering wijzigen |
| `car_share_assistant.cancel_reservation` | Reservering annuleren |
| `car_share_assistant.check_availability` | Beschikbaarheid controleren, zonder te reserveren |
| `car_share_assistant.get_reservations` | Reserveringen binnen een periode ophalen |
| `car_share_assistant.refresh` | Direct verversen |

De acties vind je onder **Tools → Acties**. Bij auto’s en personen gebruik je apparaatkeuzes op naam. In YAML zijn zowel HA-apparaat-ID’s als de stabiele `vehicle_id`/`person_id` uit de entiteitsattributen toegestaan. Bij meerdere Car share assistant-installaties selecteer je ook `config_entry_id`.

Iedere HA-gebruiker die deze acties mag uitvoeren kan een gezinslid kiezen. Er wordt geen aparte websessie per persoon gebruikt en de integratie doet niet alsof die persoon ingelogd is. De API registreert de service die de handeling uitvoert en bewaart de geselecteerde bestuurder apart. Gewone webaccounts behouden hun eigen rechten.

Voorbeeld, met **fictieve app-ID’s** die je moet vervangen:

```yaml
action: car_share_assistant.create_reservation
data:
  vehicle_id: "example-car"
  person_id: "example-person-a"
  start_time: "2026-12-12T09:00:00+01:00"
  end_time: "2026-12-12T17:00:00+01:00"
  route: "g1"
  participants:
    - "example-person-b"
  comment: "Samen naar een afspraak"
response_variable: reservering
```

Routes: `z1` eerste bestemming één keer retour, `z2` eerste bestemming twee keer retour, `g1` tweede bestemming één keer retour, `other` zelf kilometers opgeven. De namen en tarieven stel je in de webapp in. De bestuurder wordt altijd als deelnemer toegevoegd. Zodra één deelnemer is vrijgesteld, betaalt niemand voor die reservering. `kilometers` moet groter dan nul zijn bij `other`. Alle geselecteerde deelnemers delen de kosten gelijk.

`create_reservation` geeft desgewenst de reservering, ID, kostenverdeling, gebruikte `idempotency_key` en `synchronized` terug. `update_reservation` en `cancel_reservation` geven de opgeslagen reservering terug. De kalender ondersteunt geen aanmaken, wijzigen of verwijderen; daarvoor zijn uitsluitend deze acties bedoeld.

```yaml
action: car_share_assistant.cancel_reservation
data:
  reservation_id: "example-reservation"
```

Bij wijzigen stuur je naast `reservation_id` alle gewenste reserveringsvelden opnieuw. `version` is optioneel bij wijzigen/annuleren: zonder invoer haalt de integratie de huidige versie op en gebruikt die voor de gelijktijdigheidscontrole.

Beschikbaarheidscontrole en rittenopvragen vereisen antwoordgegevens. Gebruik `response_variable` in een automatisering. Beschikbaarheidscontrole reserveert of vergrendelt niets; de server controleert opnieuw bij opslaan.

## Synchronisatie en betrouwbaarheid

Standaard wordt iedere vijf minuten bijgewerkt. Dat is via de integratie-opties instelbaar van 1–60 minuten. Na een eigen wijziging wordt onmiddellijk ververst. Tijdafhankelijke sensoren worden iedere minuut bijgewerkt zonder extra reserveringsverzoeken. Kalenderperioden worden tijdelijk gecachet en de cache vervalt bij een geslaagde synchronisatie of eigen wijziging.

Mutaties worden niet automatisch opnieuw verstuurd. Een netwerkfout kan betekenen dat een reservering toch is opgeslagen: controleer eerst de planning. Voor veilig herhalen kun je vooraf zelf een `idempotency_key` instellen van 16–80 letters, cijfers of koppeltekens; gebruik dezelfde sleutel met dezelfde invoer. Als opslaan slaagt maar de daaropvolgende synchronisatie mislukt, blijft het actieantwoord succesvol met `synchronized: false`. Gebruik dan Vernieuwen.

Tijden gebruiken offsets of, als je geen tijdzone invult, de tijdzone van de app: Europe/Amsterdam. Reserveringen gebruiken hele minuten en mogen meerdere dagen duren. Het volledige interval blijft in de autokalender staan. Het gekozen ritbedrag wordt één keer geboekt op de begindatum, ook wanneer de reservering een maandgrens passeert. Tijden in het ontbrekende of dubbele uur bij zomer-/wintertijd worden geweigerd. Tarieven van bestaande ritten blijven behouden, zoals in de webapp.

## Problemen oplossen

- **Niet ontdekt:** controleer lokaal netwerk/multicast en of ontdekking in de webapp aanstaat (`CARSHARE_DISCOVERY=1`); gebruik anders Handmatig verbinden.
- **Aanmelding geweigerd:** gebruik een beheerder van de auto-app, niet je Home Assistant-account.
- **Webapp bijwerken:** deze integratieversie vereist webapp 0.4.0 of hoger voor meerdaagse reserveringen en betalingsvrijstelling.
- **Onbeschikbaar:** controleer bereikbaarheid vanaf HA en of de sleutel in de webapp is ingetrokken. Verlopen toegang start opnieuw aanmelden.
- **Adres gewijzigd:** gebruik Opnieuw configureren; verwijder de integratie niet om alleen het adres te wijzigen.
- **Conflict:** de auto is al gereserveerd of iemand heeft de rit ondertussen gewijzigd. Haal de reservering opnieuw op.
- **Geen volgende rit:** er is geen actieve/toekomstige reservering in het statusvenster van één jaar. De kalender kan wel andere perioden tonen.

De integratie controleert certificaten en volgt geen HTTP-redirects met credentials. Vul bij handmatig verbinden het uiteindelijke app-adres in. Gebruik HTTPS wanneer dat beschikbaar is. Deel wachtwoorden en API-credentials nooit in issues, screenshots of logs.

## Ontwikkelen en testen

Linux, Python 3.14.2 of hoger:

```sh
python -m venv .venv
. .venv/bin/activate
pip install -r requirements-dev.txt
ruff check custom_components tests
python -m tests.run -q
```

Tests gebruiken echte Home Assistant-coreobjecten in tijdelijke configuratiemappen, een loopback-HTTP-server en fictieve API-data. Er worden geen echte reserveringen aangemaakt. CI controleert HA 2026.11.2/2026.11.3 en hassfest.

Zie ook het [API-contract](docs/API.md) en [implementatieplan](docs/IMPLEMENTATION_PLAN.md).
