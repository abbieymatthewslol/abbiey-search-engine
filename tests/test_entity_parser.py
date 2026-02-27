"""Tests for entity detection across all 11 entity types."""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from entity_parser import detect_entities, build_search_queries, primary_entity


class TestPhoneDetection:
    def test_us_phone(self):
        entities = detect_entities("+1 555-123-4567")
        phones = [e for e in entities if e.type == "phone"]
        assert len(phones) >= 1
        assert phones[0].confidence >= 0.70

    def test_international_phone(self):
        entities = detect_entities("+44 20 7946 0958")
        phones = [e for e in entities if e.type == "phone"]
        assert len(phones) >= 1

    def test_national_format(self):
        entities = detect_entities("(555) 123-4567")
        phones = [e for e in entities if e.type == "phone"]
        assert len(phones) >= 1

    def test_short_number_rejected(self):
        entities = detect_entities("12345")
        phones = [e for e in entities if e.type == "phone"]
        assert len(phones) == 0


class TestEmailDetection:
    def test_basic_email(self):
        entities = detect_entities("user@example.com")
        emails = [e for e in entities if e.type == "email"]
        assert len(emails) == 1
        assert emails[0].normalized == "user@example.com"
        assert emails[0].meta["username"] == "user"
        assert emails[0].meta["domain"] == "example.com"

    def test_complex_email(self):
        entities = detect_entities("first.last+tag@sub.domain.co.uk")
        emails = [e for e in entities if e.type == "email"]
        assert len(emails) == 1

    def test_email_high_confidence(self):
        entities = detect_entities("test@gmail.com")
        emails = [e for e in entities if e.type == "email"]
        assert emails[0].confidence >= 0.95


class TestUsernameDetection:
    def test_at_prefix(self):
        entities = detect_entities("@johndoe")
        usernames = [e for e in entities if e.type == "username"]
        assert len(usernames) == 1
        assert usernames[0].normalized == "johndoe"

    def test_platforms_generated(self):
        entities = detect_entities("@testuser")
        usernames = [e for e in entities if e.type == "username"]
        assert len(usernames[0].meta["platforms"]) > 0

    def test_username_in_sentence(self):
        entities = detect_entities("follow me @cool_user123 on twitter")
        usernames = [e for e in entities if e.type == "username"]
        assert len(usernames) == 1


class TestDomainDetection:
    def test_basic_domain(self):
        entities = detect_entities("example.com")
        domains = [e for e in entities if e.type == "domain"]
        assert len(domains) == 1
        assert domains[0].normalized == "example.com"

    def test_subdomain(self):
        entities = detect_entities("sub.example.org")
        domains = [e for e in entities if e.type == "domain"]
        assert len(domains) >= 1

    def test_invalid_tld_rejected(self):
        entities = detect_entities("test.invalidtld")
        domains = [e for e in entities if e.type == "domain"]
        assert len(domains) == 0

    def test_email_domain_not_duplicated(self):
        """Email domain should not also appear as standalone domain."""
        entities = detect_entities("user@custom-site.com")
        domains = [e for e in entities if e.type == "domain"]
        # custom-site.com should not be a standalone domain since it's the email domain
        domain_values = [d.normalized for d in domains]
        assert "custom-site.com" not in domain_values


class TestIPDetection:
    def test_valid_ipv4(self):
        entities = detect_entities("192.168.1.1")
        ips = [e for e in entities if e.type == "ip"]
        assert len(ips) == 1

    def test_boundary_ip(self):
        entities = detect_entities("255.255.255.255")
        ips = [e for e in entities if e.type == "ip"]
        assert len(ips) == 1

    def test_zero_ip(self):
        entities = detect_entities("0.0.0.0")
        ips = [e for e in entities if e.type == "ip"]
        assert len(ips) == 1


class TestCryptoDetection:
    def test_bitcoin_legacy(self):
        entities = detect_entities("1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa")
        crypto = [e for e in entities if e.type == "crypto"]
        assert len(crypto) >= 1
        assert crypto[0].meta["chain"] == "Bitcoin"

    def test_ethereum_address(self):
        entities = detect_entities("0x742d35Cc6634C0532925a3b844Bc9e7595f2bD68")
        crypto = [e for e in entities if e.type == "crypto"]
        assert len(crypto) >= 1
        assert crypto[0].meta["chain"] == "Ethereum"

    def test_bitcoin_bech32(self):
        entities = detect_entities("bc1qar0srrr7xfkvy5l643lydnw9re59gtzzwf5mdq")
        crypto = [e for e in entities if e.type == "crypto"]
        assert len(crypto) >= 1
        assert crypto[0].meta["format"] == "bech32"


class TestMACDetection:
    def test_colon_format(self):
        entities = detect_entities("00:1A:2B:3C:4D:5E")
        macs = [e for e in entities if e.type == "mac"]
        assert len(macs) == 1
        assert macs[0].meta["oui"] == "00:1A:2B"

    def test_dash_format(self):
        entities = detect_entities("00-1A-2B-3C-4D-5E")
        macs = [e for e in entities if e.type == "mac"]
        assert len(macs) == 1

    def test_dot_format(self):
        entities = detect_entities("001A.2B3C.4D5E")
        macs = [e for e in entities if e.type == "mac"]
        assert len(macs) == 1


class TestCoordinateDetection:
    def test_basic_coords(self):
        entities = detect_entities("40.7128, -74.0060")
        coords = [e for e in entities if e.type == "coordinates"]
        assert len(coords) == 1
        assert coords[0].meta["lat"] == 40.7128
        assert coords[0].meta["lon"] == -74.006

    def test_negative_coords(self):
        entities = detect_entities("-33.8688, 151.2093")
        coords = [e for e in entities if e.type == "coordinates"]
        assert len(coords) == 1

    def test_out_of_range_rejected(self):
        """Latitude > 90 should not be detected."""
        entities = detect_entities("91.0, 0.0")
        coords = [e for e in entities if e.type == "coordinates"]
        assert len(coords) == 0

    def test_ip_not_confused_with_coords(self):
        """IP addresses should not be detected as coordinates."""
        entities = detect_entities("192.168.1.1")
        coords = [e for e in entities if e.type == "coordinates"]
        assert len(coords) == 0


class TestHashtagDetection:
    def test_basic_hashtag(self):
        entities = detect_entities("#Python")
        hashtags = [e for e in entities if e.type == "hashtag"]
        assert len(hashtags) == 1
        assert hashtags[0].meta["tag"] == "Python"

    def test_hashtag_in_text(self):
        entities = detect_entities("trending now #AI")
        hashtags = [e for e in entities if e.type == "hashtag"]
        assert len(hashtags) == 1


class TestAddressDetection:
    def test_basic_address(self):
        entities = detect_entities("123 Main Street")
        addresses = [e for e in entities if e.type == "address"]
        assert len(addresses) == 1

    def test_address_with_suffix(self):
        entities = detect_entities("456 Oak Avenue")
        addresses = [e for e in entities if e.type == "address"]
        assert len(addresses) == 1


class TestPersonDetection:
    def test_basic_name(self):
        entities = detect_entities("John Smith")
        persons = [e for e in entities if e.type == "person"]
        assert len(persons) == 1
        assert "username_guesses" in persons[0].meta
        assert len(persons[0].meta["username_guesses"]) > 0

    def test_name_not_detected_with_strong_entity(self):
        """Person names should not be detected when strong entities exist."""
        entities = detect_entities("John Smith test@example.com")
        persons = [e for e in entities if e.type == "person"]
        # Should not detect name because email has confidence >= 0.90
        assert len(persons) == 0

    def test_non_names_excluded(self):
        """Common words in _NON_NAMES should not be detected as names."""
        entities = detect_entities("Download Free")
        persons = [e for e in entities if e.type == "person"]
        assert len(persons) == 0


class TestWeatherDetection:
    def test_weather_basic(self):
        entities = detect_entities("weather London")
        weather = [e for e in entities if e.type == "weather"]
        assert len(weather) == 1
        assert weather[0].meta["location"] == "London"

    def test_weather_with_in(self):
        entities = detect_entities("weather in Tokyo")
        weather = [e for e in entities if e.type == "weather"]
        assert len(weather) == 1
        assert weather[0].meta["location"] == "Tokyo"

    def test_weather_with_for(self):
        entities = detect_entities("weather for New York")
        weather = [e for e in entities if e.type == "weather"]
        assert len(weather) == 1
        assert weather[0].meta["location"] == "New York"

    def test_temperature_keyword(self):
        entities = detect_entities("temperature Paris")
        weather = [e for e in entities if e.type == "weather"]
        assert len(weather) == 1

    def test_forecast_keyword(self):
        entities = detect_entities("forecast Berlin")
        weather = [e for e in entities if e.type == "weather"]
        assert len(weather) == 1

    def test_weather_high_confidence(self):
        entities = detect_entities("weather London")
        weather = [e for e in entities if e.type == "weather"]
        assert weather[0].confidence >= 0.90

    def test_weather_blocks_other_entities(self):
        """Weather queries should return only the weather entity."""
        entities = detect_entities("weather London")
        assert all(e.type == "weather" for e in entities)

    def test_non_weather_not_triggered(self):
        """Normal queries should not trigger weather detection."""
        entities = detect_entities("python tutorial")
        weather = [e for e in entities if e.type == "weather"]
        assert len(weather) == 0

    def test_weather_is_highest_priority(self):
        entities = detect_entities("weather London")
        result = primary_entity(entities)
        assert result.type == "weather"


class TestBuildSearchQueries:
    def test_phone_generates_queries(self):
        entities = detect_entities("+1 555-123-4567")
        queries = build_search_queries("+1 555-123-4567", entities)
        assert len(queries) > 0
        labels = [q["label"] for q in queries]
        assert any("Caller" in l or "called" in l.lower() for l in labels)

    def test_email_generates_queries(self):
        entities = detect_entities("user@example.com")
        queries = build_search_queries("user@example.com", entities)
        labels = [q["label"] for q in queries]
        assert any("Email" in l or "Username" in l for l in labels)

    def test_domain_generates_queries(self):
        entities = detect_entities("github.com")
        queries = build_search_queries("github.com", entities)
        labels = [q["label"] for q in queries]
        assert any("WHOIS" in l or "Site" in l for l in labels)


class TestPrimaryEntity:
    def test_returns_none_for_empty(self):
        assert primary_entity([]) is None

    def test_highest_priority_wins(self):
        entities = detect_entities("test@example.com example.com")
        result = primary_entity(entities)
        # Email (priority 9) should win over domain (priority 3)
        assert result.type == "email"

    def test_phone_highest_priority(self):
        entities = detect_entities("+1 555-123-4567 #trending")
        result = primary_entity(entities)
        assert result.type == "phone"


class TestConfidenceScores:
    def test_email_high_confidence(self):
        entities = detect_entities("admin@company.com")
        emails = [e for e in entities if e.type == "email"]
        assert emails[0].confidence >= 0.95

    def test_person_low_confidence(self):
        entities = detect_entities("Jane Doe")
        persons = [e for e in entities if e.type == "person"]
        if persons:
            assert persons[0].confidence < 0.80

    def test_ip_high_confidence(self):
        entities = detect_entities("10.0.0.1")
        ips = [e for e in entities if e.type == "ip"]
        assert ips[0].confidence >= 0.90
