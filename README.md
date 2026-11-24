# Car share assistant voor Home Assistant

In ontwikkeling: een custom integratie voor de zelfstandige Car share assistant-webapp voor gezinsauto’s. Dit project gebruikt de eigen service-API van Car share assistant, zonder verbinding met Wheelshare.

**Status:** de repository en API-specificatie zijn beschikbaar. De Home Assistant-integratie en eerste installeerbare release moeten nog worden gebouwd. Deze repository is dus nog niet via de Marketplace of HACS te installeren.

Geplande functies:

- Eén apparaat per auto met een uitsluitend leesbare kalender. Afspraken tonen bestuurder, begin, einde, deelnemers en opmerking.
- Eén apparaat per gezinslid met kosten van deze en vorige maand, aantal ritten en de volgende reservering.
- Algemene acties om reserveringen aan te maken, te wijzigen of te annuleren, beschikbaarheid te controleren en te vernieuwen.
- Bij reserveren kies je expliciet de auto, de persoon, tijden, route, kilometers, medereizigers en opmerking. De Home Assistant-sleutel mag reserveringen voor alle gezinsleden beheren.
- Configuratie via de interface: app-adres en een intrekbare API-sleutel. Geen webwachtwoorden of sessiecookies nodig.

Persoonlijke kalenders en persoonlijke snelacties zijn optioneel voor later. Eén algemene reserveringsactie met een persoonskeuze vormt de basis.

Zie de [service-API](docs/API.md) en het [implementatieplan](docs/IMPLEMENTATION_PLAN.md).

De uiteindelijke installatie loopt via een custom repository in de [Home Assistant Marketplace](https://www.home-assistant.io/integrations/marketplace/#custom-repositories). Er is nog geen release gepubliceerd.
