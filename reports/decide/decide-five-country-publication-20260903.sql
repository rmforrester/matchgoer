BEGIN;

CREATE TEMP TABLE decide_approved_catalogue (
    subject_type text NOT NULL, team_a_id integer, team_b_id integer, venue_id integer, team_id integer,
    attribute_key text NOT NULL, label text NOT NULL, explanation text NOT NULL, lead_priority text NOT NULL,
    evidence_url text, evidence_season text, evidence_note text
) ON COMMIT DROP;

INSERT INTO decide_approved_catalogue VALUES
    ('TEAM_PAIR', 33, 40, NULL, NULL, 'SIGNIFICANT_RIVALRY', 'North-West rivalry', 'A fixture with genuine rivalry context worth knowing before choosing the match.', 'NORMAL', NULL, NULL, NULL),
    ('TEAM_PAIR', 42, 47, NULL, NULL, 'SIGNIFICANT_RIVALRY', 'North London Derby', 'A fixture with genuine rivalry context worth knowing before choosing the match.', 'NORMAL', NULL, NULL, NULL),
    ('TEAM_PAIR', 33, 50, NULL, NULL, 'SIGNIFICANT_RIVALRY', 'Manchester Derby', 'A fixture with genuine rivalry context worth knowing before choosing the match.', 'NORMAL', NULL, NULL, NULL),
    ('TEAM_PAIR', 42, 49, NULL, NULL, 'SIGNIFICANT_RIVALRY', 'London rivalry', 'A fixture with genuine rivalry context worth knowing before choosing the match.', 'NORMAL', NULL, NULL, NULL),
    ('TEAM_PAIR', 47, 49, NULL, NULL, 'SIGNIFICANT_RIVALRY', 'London rivalry', 'A fixture with genuine rivalry context worth knowing before choosing the match.', 'NORMAL', NULL, NULL, NULL),
    ('TEAM_PAIR', 48, 58, NULL, NULL, 'SIGNIFICANT_RIVALRY', 'London rivalry', 'A fixture with genuine rivalry context worth knowing before choosing the match.', 'NORMAL', NULL, NULL, NULL),
    ('TEAM_PAIR', 47, 48, NULL, NULL, 'SIGNIFICANT_RIVALRY', 'London rivalry', 'A fixture with genuine rivalry context worth knowing before choosing the match.', 'NORMAL', NULL, NULL, NULL),
    ('TEAM_PAIR', 36, 49, NULL, NULL, 'SIGNIFICANT_RIVALRY', 'West London derby', 'A fixture with genuine rivalry context worth knowing before choosing the match.', 'NORMAL', NULL, NULL, NULL),
    ('TEAM_PAIR', 40, 45, NULL, NULL, 'SIGNIFICANT_RIVALRY', 'Merseyside Derby', 'A fixture with genuine rivalry context worth knowing before choosing the match.', 'NORMAL', NULL, NULL, NULL),
    ('TEAM_PAIR', 34, 746, NULL, NULL, 'SIGNIFICANT_RIVALRY', 'Tyne-Wear Derby', 'A fixture with genuine rivalry context worth knowing before choosing the match.', 'NORMAL', NULL, NULL, NULL),
    ('TEAM_PAIR', 54, 66, NULL, NULL, 'SIGNIFICANT_RIVALRY', 'Second City Derby', 'A fixture with genuine rivalry context worth knowing before choosing the match.', 'NORMAL', NULL, NULL, NULL),
    ('TEAM_PAIR', 39, 60, NULL, NULL, 'SIGNIFICANT_RIVALRY', 'Black Country Derby', 'A fixture with genuine rivalry context worth knowing before choosing the match.', 'NORMAL', NULL, NULL, NULL),
    ('TEAM_PAIR', 44, 67, NULL, NULL, 'SIGNIFICANT_RIVALRY', 'East Lancashire Derby', 'A fixture with genuine rivalry context worth knowing before choosing the match.', 'NORMAL', NULL, NULL, NULL),
    ('TEAM_PAIR', 62, 74, NULL, NULL, 'SIGNIFICANT_RIVALRY', 'Steel City Derby', 'A fixture with genuine rivalry context worth knowing before choosing the match.', 'NORMAL', NULL, NULL, NULL),
    ('TEAM_PAIR', 41, 1355, NULL, NULL, 'SIGNIFICANT_RIVALRY', 'South Coast Derby', 'A fixture with genuine rivalry context worth knowing before choosing the match.', 'NORMAL', NULL, NULL, NULL),
    ('TEAM_PAIR', 57, 71, NULL, NULL, 'SIGNIFICANT_RIVALRY', 'East Anglian Derby', 'A fixture with genuine rivalry context worth knowing before choosing the match.', 'NORMAL', NULL, NULL, NULL),
    ('TEAM_PAIR', 56, 1334, NULL, NULL, 'SIGNIFICANT_RIVALRY', 'Bristol Derby', 'A fixture with genuine rivalry context worth knowing before choosing the match.', 'NORMAL', NULL, NULL, NULL),
    ('TEAM_PAIR', 1357, 1364, NULL, NULL, 'SIGNIFICANT_RIVALRY', 'Devon Derby', 'A fixture with genuine rivalry context worth knowing before choosing the match.', 'NORMAL', NULL, NULL, NULL),
    ('TEAM_PAIR', 1338, 1353, NULL, NULL, 'SIGNIFICANT_RIVALRY', 'A420 rivalry', 'A fixture with genuine rivalry context worth knowing before choosing the match.', 'NORMAL', NULL, NULL, NULL),
    ('TEAM_PAIR', 59, 1356, NULL, NULL, 'SIGNIFICANT_RIVALRY', 'West Lancashire Derby', 'A fixture with genuine rivalry context worth knowing before choosing the match.', 'NORMAL', NULL, NULL, NULL),
    ('TEAM_PAIR', 1345, 1374, NULL, NULL, 'SIGNIFICANT_RIVALRY', 'Derbyshire/Nottinghamshire rivalry', 'A fixture with genuine rivalry context worth knowing before choosing the match.', 'NORMAL', NULL, NULL, NULL),
    ('TEAM_PAIR', 1820, 1837, NULL, NULL, 'SIGNIFICANT_RIVALRY', 'Cross-border derby', 'A fixture with genuine rivalry context worth knowing before choosing the match.', 'NORMAL', NULL, NULL, NULL),
    ('TEAM_PAIR', 33, 63, NULL, NULL, 'SIGNIFICANT_RIVALRY', 'Historic rivalry', 'A fixture with genuine rivalry context worth knowing before choosing the match.', 'NORMAL', NULL, NULL, NULL),
    ('TEAM_PAIR', 37, 63, NULL, NULL, 'SIGNIFICANT_RIVALRY', 'West Yorkshire derby', 'A fixture with genuine rivalry context worth knowing before choosing the match.', 'NORMAL', NULL, NULL, NULL),
    ('TEAM_PAIR', 65, 69, NULL, NULL, 'SIGNIFICANT_RIVALRY', 'East Midlands Derby', 'A fixture with genuine rivalry context worth knowing before choosing the match.', 'NORMAL', NULL, NULL, NULL),
    ('TEAM_PAIR', 46, 69, NULL, NULL, 'SIGNIFICANT_RIVALRY', 'East Midlands rivalry', 'A fixture with genuine rivalry context worth knowing before choosing the match.', 'NORMAL', NULL, NULL, NULL),
    ('TEAM_PAIR', 46, 1346, NULL, NULL, 'SIGNIFICANT_RIVALRY', 'M69 Derby', 'A fixture with genuine rivalry context worth knowing before choosing the match.', 'NORMAL', NULL, NULL, NULL),
    ('TEAM_PAIR', 51, 52, NULL, NULL, 'SIGNIFICANT_RIVALRY', 'Historic rivalry', 'A fixture with genuine rivalry context worth knowing before choosing the match.', 'NORMAL', NULL, NULL, NULL),
    ('TEAM_PAIR', 61, 68, NULL, NULL, 'SIGNIFICANT_RIVALRY', 'Greater Manchester/Lancashire rivalry', 'A fixture with genuine rivalry context worth knowing before choosing the match.', 'NORMAL', NULL, NULL, NULL),
    ('TEAM_PAIR', 1350, 1370, NULL, NULL, 'SIGNIFICANT_RIVALRY', 'Cambridgeshire rivalry', 'A fixture with genuine rivalry context worth knowing before choosing the match.', 'NORMAL', NULL, NULL, NULL),
    ('TEAM_PAIR', 1341, 1361, NULL, NULL, 'SIGNIFICANT_RIVALRY', 'Essex derby', 'A fixture with genuine rivalry context worth knowing before choosing the match.', 'NORMAL', NULL, NULL, NULL),
    ('TEAM_PAIR', 1340, 1365, NULL, NULL, 'SIGNIFICANT_RIVALRY', 'Lincolnshire rivalry', 'A fixture with genuine rivalry context worth knowing before choosing the match.', 'NORMAL', NULL, NULL, NULL),
    ('TEAM_PAIR', 1374, 1376, NULL, NULL, 'SIGNIFICANT_RIVALRY', 'Nottinghamshire derby', 'A fixture with genuine rivalry context worth knowing before choosing the match.', 'NORMAL', NULL, NULL, NULL),
    ('TEAM_PAIR', 1365, 1379, NULL, NULL, 'SIGNIFICANT_RIVALRY', 'Lincolnshire derby', 'A fixture with genuine rivalry context worth knowing before choosing the match.', 'NORMAL', NULL, NULL, NULL),
    ('TEAM_PAIR', 1339, 1349, NULL, NULL, 'SIGNIFICANT_RIVALRY', 'Greater Manchester derby', 'A fixture with genuine rivalry context worth knowing before choosing the match.', 'NORMAL', NULL, NULL, NULL),
    ('TEAM_PAIR', 1371, 1819, NULL, NULL, 'SIGNIFICANT_RIVALRY', 'Cumbrian derby', 'A fixture with genuine rivalry context worth knowing before choosing the match.', 'NORMAL', NULL, NULL, NULL),
    ('TEAM_PAIR', 75, 1351, NULL, NULL, 'SIGNIFICANT_RIVALRY', 'Potteries Derby', 'A fixture with genuine rivalry context worth knowing before choosing the match.', 'NORMAL', NULL, NULL, NULL),
    ('TEAM_PAIR', 38, 1359, NULL, NULL, 'SIGNIFICANT_RIVALRY', 'Beds-Herts rivalry', 'A fixture with genuine rivalry context worth knowing before choosing the match.', 'NORMAL', NULL, NULL, NULL),
    ('TEAM_PAIR', 58, 1335, NULL, NULL, 'SIGNIFICANT_RIVALRY', 'South London derby', 'A fixture with genuine rivalry context worth knowing before choosing the match.', 'NORMAL', NULL, NULL, NULL),
    ('TEAM_PAIR', 1333, 1348, NULL, NULL, 'SIGNIFICANT_RIVALRY', 'Modern historic rivalry', 'A fixture with genuine rivalry context worth knowing before choosing the match.', 'NORMAL', NULL, NULL, NULL),
    ('VENUE', NULL, NULL, 582, NULL, 'CLASSIC_GROUND', 'Classic ground', 'A surviving traditional football experience with character, continuity and matchday identity.', 'NORMAL', NULL, NULL, NULL),
    ('VENUE', NULL, NULL, 573, NULL, 'CLASSIC_GROUND', 'Classic ground', 'A surviving traditional football experience with character, continuity and matchday identity.', 'NORMAL', NULL, NULL, NULL),
    ('VENUE', NULL, NULL, 20414, NULL, 'CLASSIC_GROUND', 'Classic ground', 'A surviving traditional football experience with character, continuity and matchday identity.', 'NORMAL', NULL, NULL, NULL),
    ('VENUE', NULL, NULL, 495, NULL, 'CLASSIC_GROUND', 'Classic ground', 'A surviving traditional football experience with character, continuity and matchday identity.', 'NORMAL', NULL, NULL, NULL),
    ('VENUE', NULL, NULL, 535, NULL, 'CLASSIC_GROUND', 'Classic ground', 'A surviving traditional football experience with character, continuity and matchday identity.', 'NORMAL', NULL, NULL, NULL),
    ('VENUE', NULL, NULL, 574, NULL, 'CLASSIC_GROUND', 'Classic ground', 'A surviving traditional football experience with character, continuity and matchday identity.', 'NORMAL', NULL, NULL, NULL),
    ('VENUE', NULL, NULL, 518, NULL, 'CLASSIC_GROUND', 'Classic ground', 'A surviving traditional football experience with character, continuity and matchday identity.', 'NORMAL', NULL, NULL, NULL),
    ('VENUE', NULL, NULL, 551, NULL, 'CLASSIC_GROUND', 'Classic ground', 'A surviving traditional football experience with character, continuity and matchday identity.', 'NORMAL', NULL, NULL, NULL),
    ('VENUE', NULL, NULL, 512, NULL, 'CLASSIC_GROUND', 'Classic ground', 'A surviving traditional football experience with character, continuity and matchday identity.', 'NORMAL', NULL, NULL, NULL),
    ('VENUE', NULL, NULL, 546, NULL, 'CLASSIC_GROUND', 'Classic ground', 'A surviving traditional football experience with character, continuity and matchday identity.', 'NORMAL', NULL, NULL, NULL),
    ('VENUE', NULL, NULL, 566, NULL, 'CLASSIC_GROUND', 'Classic ground', 'A surviving traditional football experience with character, continuity and matchday identity.', 'NORMAL', NULL, NULL, NULL),
    ('VENUE', NULL, NULL, 500, NULL, 'CLASSIC_GROUND', 'Classic ground', 'A surviving traditional football experience with character, continuity and matchday identity.', 'NORMAL', NULL, NULL, NULL),
    ('VENUE', NULL, NULL, 568, NULL, 'CLASSIC_GROUND', 'Classic ground', 'A surviving traditional football experience with character, continuity and matchday identity.', 'NORMAL', NULL, NULL, NULL),
    ('VENUE', NULL, NULL, 517, NULL, 'CLASSIC_GROUND', 'Classic ground', 'A surviving traditional football experience with character, continuity and matchday identity.', 'NORMAL', NULL, NULL, NULL),
    ('VENUE', NULL, NULL, 538, NULL, 'CLASSIC_GROUND', 'Classic ground', 'A surviving traditional football experience with character, continuity and matchday identity.', 'NORMAL', NULL, NULL, NULL),
    ('VENUE', NULL, NULL, 597, NULL, 'CLASSIC_GROUND', 'Classic ground', 'A surviving traditional football experience with character, continuity and matchday identity.', 'NORMAL', NULL, NULL, NULL),
    ('VENUE', NULL, NULL, 581, NULL, 'CLASSIC_GROUND', 'Classic ground', 'A surviving traditional football experience with character, continuity and matchday identity.', 'NORMAL', NULL, NULL, NULL),
    ('VENUE', NULL, NULL, 3535, NULL, 'CLASSIC_GROUND', 'Classic ground', 'A surviving traditional football experience with character, continuity and matchday identity.', 'NORMAL', NULL, NULL, NULL),
    ('VENUE', NULL, NULL, 586, NULL, 'CLASSIC_GROUND', 'Classic ground', 'A surviving traditional football experience with character, continuity and matchday identity.', 'NORMAL', NULL, NULL, NULL),
    ('VENUE', NULL, NULL, 18618, NULL, 'CLASSIC_GROUND', 'Classic ground', 'A surviving traditional football experience with character, continuity and matchday identity.', 'NORMAL', NULL, NULL, NULL),
    ('VENUE', NULL, NULL, 537, NULL, 'CLASSIC_GROUND', 'Classic ground', 'A surviving traditional football experience with character, continuity and matchday identity.', 'NORMAL', NULL, NULL, NULL),
    ('VENUE', NULL, NULL, 556, NULL, 'FOOTBALL_LANDMARK', 'Football landmark', 'A ground with exceptional significance in English football history.', 'NORMAL', NULL, NULL, NULL),
    ('VENUE', NULL, NULL, 550, NULL, 'FOOTBALL_LANDMARK', 'Football landmark', 'A ground with exceptional significance in English football history.', 'NORMAL', NULL, NULL, NULL),
    ('VENUE', NULL, NULL, 495, NULL, 'FOOTBALL_LANDMARK', 'Football landmark', 'A ground with exceptional significance in English football history.', 'NORMAL', NULL, NULL, NULL),
    ('VENUE', NULL, NULL, 581, NULL, 'FOOTBALL_LANDMARK', 'Football landmark', 'A ground with exceptional significance in English football history.', 'NORMAL', NULL, NULL, NULL),
    ('VENUE', NULL, NULL, 574, NULL, 'FOOTBALL_LANDMARK', 'Football landmark', 'A ground with exceptional significance in English football history.', 'NORMAL', NULL, NULL, NULL),
    ('VENUE', NULL, NULL, 582, NULL, 'FOOTBALL_LANDMARK', 'Football landmark', 'A ground with exceptional significance in English football history.', 'NORMAL', NULL, NULL, NULL),
    ('VENUE', NULL, NULL, 519, NULL, 'FOOTBALL_LANDMARK', 'Football landmark', 'A ground with exceptional significance in English football history.', 'NORMAL', NULL, NULL, NULL),
    ('VENUE', NULL, NULL, 535, NULL, 'UNIQUE_SETTING', 'Thames-side setting', 'A distinctive riverside football setting on the Thames.', 'LEAD', NULL, NULL, NULL),
    ('VENUE', NULL, NULL, 562, NULL, 'UNIQUE_SETTING', 'City-centre setting', 'A major football ground embedded prominently in central Newcastle.', 'NORMAL', NULL, NULL, NULL),
    ('VENUE', NULL, NULL, 551, NULL, 'UNIQUE_SETTING', 'Neighbourhood setting', 'An extraordinary football ground woven directly into its surrounding residential streets.', 'LEAD', NULL, NULL, NULL),
    ('VENUE', NULL, NULL, 568, NULL, 'UNIQUE_SETTING', 'Pennine setting', 'An exposed, elevated football setting shaped by its Pennine location.', 'NORMAL', NULL, NULL, NULL),
    ('TEAM_PAIR', 165, 174, NULL, NULL, 'SIGNIFICANT_RIVALRY', 'Revierderby', 'A genuine German rivalry fixture with additional matchgoing significance.', 'NORMAL', NULL, NULL, NULL),
    ('TEAM_PAIR', 175, 186, NULL, NULL, 'SIGNIFICANT_RIVALRY', 'Hamburg Derby', 'A genuine German rivalry fixture with additional matchgoing significance.', 'NORMAL', NULL, NULL, NULL),
    ('TEAM_PAIR', 163, 192, NULL, NULL, 'SIGNIFICANT_RIVALRY', 'Rheinland derby', 'A genuine German rivalry fixture with additional matchgoing significance.', 'NORMAL', NULL, NULL, NULL),
    ('TEAM_PAIR', 171, 178, NULL, NULL, 'SIGNIFICANT_RIVALRY', 'Frankenderby', 'A genuine German rivalry fixture with additional matchgoing significance.', 'NORMAL', NULL, NULL, NULL),
    ('TEAM_PAIR', 157, 165, NULL, NULL, 'SIGNIFICANT_RIVALRY', 'German heavyweight rivalry', 'A genuine German rivalry fixture with additional matchgoing significance.', 'NORMAL', NULL, NULL, NULL),
    ('TEAM_PAIR', 157, 163, NULL, NULL, 'SIGNIFICANT_RIVALRY', 'Historic Klassiker', 'A genuine German rivalry fixture with additional matchgoing significance.', 'NORMAL', NULL, NULL, NULL),
    ('TEAM_PAIR', 162, 175, NULL, NULL, 'SIGNIFICANT_RIVALRY', 'Nordderby', 'A genuine German rivalry fixture with additional matchgoing significance.', 'NORMAL', NULL, NULL, NULL),
    ('TEAM_PAIR', 166, 744, NULL, NULL, 'SIGNIFICANT_RIVALRY', 'Lower Saxony derby', 'A genuine German rivalry fixture with additional matchgoing significance.', 'NORMAL', NULL, NULL, NULL),
    ('TEAM_PAIR', 187, 1621, NULL, NULL, 'SIGNIFICANT_RIVALRY', 'Revierderby', 'A genuine German rivalry fixture with additional matchgoing significance.', 'NORMAL', NULL, NULL, NULL),
    ('TEAM_PAIR', 179, 183, NULL, NULL, 'SIGNIFICANT_RIVALRY', 'East German rivalry', 'A genuine German rivalry fixture with additional matchgoing significance.', 'NORMAL', NULL, NULL, NULL),
    ('TEAM_PAIR', 745, 1639, NULL, NULL, 'SIGNIFICANT_RIVALRY', 'Southwest rivalry', 'A genuine German rivalry fixture with additional matchgoing significance.', 'NORMAL', NULL, NULL, NULL),
    ('TEAM_PAIR', 172, 785, NULL, NULL, 'SIGNIFICANT_RIVALRY', 'Baden-Württemberg rivalry', 'A genuine German rivalry fixture with additional matchgoing significance.', 'NORMAL', NULL, NULL, NULL),
    ('TEAM_PAIR', 745, 785, NULL, NULL, 'SIGNIFICANT_RIVALRY', 'Southwest rivalry', 'A genuine German rivalry fixture with additional matchgoing significance.', 'NORMAL', NULL, NULL, NULL),
    ('TEAM_PAIR', 745, 4268, NULL, NULL, 'SIGNIFICANT_RIVALRY', 'Southwest rivalry', 'A genuine German rivalry fixture with additional matchgoing significance.', 'NORMAL', NULL, NULL, NULL),
    ('TEAM_PAIR', 174, 1621, NULL, NULL, 'SIGNIFICANT_RIVALRY', 'Ruhr rivalry', 'A genuine German rivalry fixture with additional matchgoing significance.', 'NORMAL', NULL, NULL, NULL),
    ('TEAM_PAIR', 186, 1321, NULL, NULL, 'SIGNIFICANT_RIVALRY', 'North German rivalry', 'A genuine German rivalry fixture with additional matchgoing significance.', 'NORMAL', NULL, NULL, NULL),
    ('TEAM_PAIR', 183, 9355, NULL, NULL, 'SIGNIFICANT_RIVALRY', 'East German rivalry', 'A genuine German rivalry fixture with additional matchgoing significance.', 'NORMAL', NULL, NULL, NULL),
    ('TEAM_PAIR', 179, 1316, NULL, NULL, 'SIGNIFICANT_RIVALRY', 'Saxony-Anhalt derby', 'A genuine German rivalry fixture with additional matchgoing significance.', 'NORMAL', NULL, NULL, NULL),
    ('TEAM_PAIR', 157, 175, NULL, NULL, 'SIGNIFICANT_RIVALRY', 'Historic North-South rivalry', 'A genuine German rivalry fixture with additional matchgoing significance.', 'NORMAL', NULL, NULL, NULL),
    ('VENUE', NULL, NULL, 23073, NULL, 'CLASSIC_GROUND', 'Classic ground', 'A traditional German football ground whose character and continuity add to the matchday.', 'NORMAL', NULL, NULL, NULL),
    ('VENUE', NULL, NULL, 23064, NULL, 'CLASSIC_GROUND', 'Classic ground', 'A traditional German football ground whose character and continuity add to the matchday.', 'NORMAL', NULL, NULL, NULL),
    ('VENUE', NULL, NULL, 23076, NULL, 'CLASSIC_GROUND', 'Classic ground', 'A traditional German football ground whose character and continuity add to the matchday.', 'NORMAL', NULL, NULL, NULL),
    ('VENUE', NULL, NULL, 23069, NULL, 'CLASSIC_GROUND', 'Classic ground', 'A traditional German football ground whose character and continuity add to the matchday.', 'NORMAL', NULL, NULL, NULL),
    ('VENUE', NULL, NULL, 23063, NULL, 'CLASSIC_GROUND', 'Classic ground', 'A traditional German football ground whose character and continuity add to the matchday.', 'NORMAL', NULL, NULL, NULL),
    ('VENUE', NULL, NULL, 23067, NULL, 'CLASSIC_GROUND', 'Classic ground', 'A traditional German football ground whose character and continuity add to the matchday.', 'NORMAL', NULL, NULL, NULL),
    ('VENUE', NULL, NULL, 23072, NULL, 'CLASSIC_GROUND', 'Classic ground', 'A traditional German football ground whose character and continuity add to the matchday.', 'NORMAL', NULL, NULL, NULL),
    ('VENUE', NULL, NULL, 23070, NULL, 'CLASSIC_GROUND', 'Classic ground', 'A traditional German football ground whose character and continuity add to the matchday.', 'NORMAL', NULL, NULL, NULL),
    ('VENUE', NULL, NULL, 23071, NULL, 'CLASSIC_GROUND', 'Classic ground', 'A traditional German football ground whose character and continuity add to the matchday.', 'NORMAL', NULL, NULL, NULL),
    ('VENUE', NULL, NULL, 23068, NULL, 'CLASSIC_GROUND', 'Classic ground', 'A traditional German football ground whose character and continuity add to the matchday.', 'NORMAL', NULL, NULL, NULL),
    ('VENUE', NULL, NULL, 23062, NULL, 'CLASSIC_GROUND', 'Classic ground', 'A traditional German football ground whose character and continuity add to the matchday.', 'NORMAL', NULL, NULL, NULL),
    ('VENUE', NULL, NULL, 23374, NULL, 'CLASSIC_GROUND', 'Classic ground', 'A traditional German football ground whose character and continuity add to the matchday.', 'NORMAL', NULL, NULL, NULL),
    ('VENUE', NULL, NULL, 23059, NULL, 'FOOTBALL_LANDMARK', 'Football landmark', 'A venue with exceptional significance in German football history.', 'NORMAL', NULL, NULL, NULL),
    ('VENUE', NULL, NULL, 23073, NULL, 'FOOTBALL_LANDMARK', 'Football landmark', 'A venue with exceptional significance in German football history.', 'NORMAL', NULL, NULL, NULL),
    ('VENUE', NULL, NULL, 23062, NULL, 'FOOTBALL_LANDMARK', 'Football landmark', 'A venue with exceptional significance in German football history.', 'NORMAL', NULL, NULL, NULL),
    ('VENUE', NULL, NULL, 23073, NULL, 'UNIQUE_SETTING', 'Betzenberg setting', 'A near-50,000-capacity ground towering above the city on the Betzenberg.', 'LEAD', NULL, NULL, NULL),
    ('VENUE', NULL, NULL, 23066, NULL, 'UNIQUE_SETTING', 'Germany''s highest pro ground', 'The highest stadium in German professional football, around 555m above sea level.', 'LEAD', NULL, NULL, NULL),
    ('TEAM', NULL, NULL, NULL, 1321, 'EXCEPTIONAL_SUPPORT', 'Exceptional support', '2025/26 average home attendance 24,948, around 2.38× the 3. Liga average.', 'LEAD', 'https://www.dfb.de/news/rekorde-talente-fans-die-highlightfakten-der-3-liga', '2025/26', '2025/26 completed season; league average 10,470.'),
    ('TEAM', NULL, NULL, NULL, 4259, 'EXCEPTIONAL_SUPPORT', 'Exceptional support', '2025/26 average home attendance 23,098, around 2.21× the 3. Liga average.', 'LEAD', 'https://www.dfb.de/news/rekorde-talente-fans-die-highlightfakten-der-3-liga', '2025/26', '2025/26 completed season; league average 10,470.'),
    ('TEAM', NULL, NULL, NULL, 187, 'EXCEPTIONAL_SUPPORT', 'Exceptional support', '2025/26 average home attendance 22,949, around 2.19× the 3. Liga average.', 'LEAD', 'https://www.dfb.de/news/rekorde-talente-fans-die-highlightfakten-der-3-liga', '2025/26', '2025/26 completed season; league average 10,470.'),
    ('TEAM', NULL, NULL, NULL, 1621, 'EXCEPTIONAL_SUPPORT', 'Exceptional support', '2025/26 average home attendance 17,361, around 1.66× the 3. Liga average.', 'LEAD', 'https://www.dfb.de/news/rekorde-talente-fans-die-highlightfakten-der-3-liga', '2025/26', '2025/26 completed season; league average 10,470.'),
    ('TEAM_PAIR', 529, 541, NULL, NULL, 'SIGNIFICANT_RIVALRY', 'El Clásico', 'A genuine Spanish rivalry or derby that adds meaningful context to the fixture.', 'NORMAL', NULL, NULL, NULL),
    ('TEAM_PAIR', 530, 541, NULL, NULL, 'SIGNIFICANT_RIVALRY', 'Madrid Derby', 'A genuine Spanish rivalry or derby that adds meaningful context to the fixture.', 'NORMAL', NULL, NULL, NULL),
    ('TEAM_PAIR', 529, 540, NULL, NULL, 'SIGNIFICANT_RIVALRY', 'Barcelona Derby', 'A genuine Spanish rivalry or derby that adds meaningful context to the fixture.', 'NORMAL', NULL, NULL, NULL),
    ('TEAM_PAIR', 536, 543, NULL, NULL, 'SIGNIFICANT_RIVALRY', 'Seville Derby', 'A genuine Spanish rivalry or derby that adds meaningful context to the fixture.', 'NORMAL', NULL, NULL, NULL),
    ('TEAM_PAIR', 531, 548, NULL, NULL, 'SIGNIFICANT_RIVALRY', 'Basque Derby', 'A genuine Spanish rivalry or derby that adds meaningful context to the fixture.', 'NORMAL', NULL, NULL, NULL),
    ('TEAM_PAIR', 718, 731, NULL, NULL, 'SIGNIFICANT_RIVALRY', 'Asturian Derby', 'A genuine Spanish rivalry or derby that adds meaningful context to the fixture.', 'NORMAL', NULL, NULL, NULL),
    ('TEAM_PAIR', 538, 544, NULL, NULL, 'SIGNIFICANT_RIVALRY', 'Galician Derby', 'A genuine Spanish rivalry or derby that adds meaningful context to the fixture.', 'NORMAL', NULL, NULL, NULL),
    ('TEAM_PAIR', 532, 539, NULL, NULL, 'SIGNIFICANT_RIVALRY', 'Valencia Derby', 'A genuine Spanish rivalry or derby that adds meaningful context to the fixture.', 'NORMAL', NULL, NULL, NULL),
    ('TEAM_PAIR', 532, 533, NULL, NULL, 'SIGNIFICANT_RIVALRY', 'Valencian rivalry', 'A genuine Spanish rivalry or derby that adds meaningful context to the fixture.', 'NORMAL', NULL, NULL, NULL),
    ('TEAM_PAIR', 543, 724, NULL, NULL, 'SIGNIFICANT_RIVALRY', 'Andalusian rivalry', 'A genuine Spanish rivalry or derby that adds meaningful context to the fixture.', 'NORMAL', NULL, NULL, NULL),
    ('TEAM_PAIR', 535, 715, NULL, NULL, 'SIGNIFICANT_RIVALRY', 'Andalusian rivalry', 'A genuine Spanish rivalry or derby that adds meaningful context to the fixture.', 'NORMAL', NULL, NULL, NULL),
    ('TEAM_PAIR', 534, 719, NULL, NULL, 'SIGNIFICANT_RIVALRY', 'Canary Islands Derby', 'A genuine Spanish rivalry or derby that adds meaningful context to the fixture.', 'NORMAL', NULL, NULL, NULL),
    ('TEAM_PAIR', 5262, 5275, NULL, NULL, 'SIGNIFICANT_RIVALRY', 'Murcia regional derby', 'A genuine Spanish rivalry or derby that adds meaningful context to the fixture.', 'NORMAL', NULL, NULL, NULL),
    ('TEAM_PAIR', 797, 4666, NULL, NULL, 'SIGNIFICANT_RIVALRY', 'Alicante provincial derby', 'A genuine Spanish rivalry or derby that adds meaningful context to the fixture.', 'NORMAL', NULL, NULL, NULL),
    ('TEAM_PAIR', 531, 727, NULL, NULL, 'SIGNIFICANT_RIVALRY', 'Northern regional rivalry', 'A genuine Spanish rivalry or derby that adds meaningful context to the fixture.', 'NORMAL', NULL, NULL, NULL),
    ('TEAM_PAIR', 548, 727, NULL, NULL, 'SIGNIFICANT_RIVALRY', 'Northern regional rivalry', 'A genuine Spanish rivalry or derby that adds meaningful context to the fixture.', 'NORMAL', NULL, NULL, NULL),
    ('TEAM_PAIR', 545, 548, NULL, NULL, 'SIGNIFICANT_RIVALRY', 'Basque regional rivalry', 'A genuine Spanish rivalry or derby that adds meaningful context to the fixture.', 'NORMAL', NULL, NULL, NULL),
    ('VENUE', NULL, NULL, 23263, NULL, 'CLASSIC_GROUND', 'Classic ground', 'A Spanish ground whose surviving character and football continuity make it worth seeking out.', 'NORMAL', NULL, NULL, NULL),
    ('VENUE', NULL, NULL, 23276, NULL, 'CLASSIC_GROUND', 'Classic ground', 'A Spanish ground whose surviving character and football continuity make it worth seeking out.', 'NORMAL', NULL, NULL, NULL),
    ('VENUE', NULL, NULL, 23265, NULL, 'CLASSIC_GROUND', 'Classic ground', 'A Spanish ground whose surviving character and football continuity make it worth seeking out.', 'NORMAL', NULL, NULL, NULL),
    ('VENUE', NULL, NULL, 23564, NULL, 'CLASSIC_GROUND', 'Classic ground', 'A Spanish ground whose surviving character and football continuity make it worth seeking out.', 'NORMAL', NULL, NULL, NULL),
    ('VENUE', NULL, NULL, 23266, NULL, 'CLASSIC_GROUND', 'Classic ground', 'A Spanish ground whose surviving character and football continuity make it worth seeking out.', 'NORMAL', NULL, NULL, NULL),
    ('VENUE', NULL, NULL, 23233, NULL, 'CLASSIC_GROUND', 'Classic ground', 'A Spanish ground whose surviving character and football continuity make it worth seeking out.', 'NORMAL', NULL, NULL, NULL),
    ('VENUE', NULL, NULL, 23278, NULL, 'CLASSIC_GROUND', 'Classic ground', 'A Spanish ground whose surviving character and football continuity make it worth seeking out.', 'NORMAL', NULL, NULL, NULL),
    ('VENUE', NULL, NULL, 23563, NULL, 'CLASSIC_GROUND', 'Classic ground', 'A Spanish ground whose surviving character and football continuity make it worth seeking out.', 'NORMAL', NULL, NULL, NULL),
    ('VENUE', NULL, NULL, 23272, NULL, 'CLASSIC_GROUND', 'Classic ground', 'A Spanish ground whose surviving character and football continuity make it worth seeking out.', 'NORMAL', NULL, NULL, NULL),
    ('VENUE', NULL, NULL, 23559, NULL, 'CLASSIC_GROUND', 'Classic ground', 'A Spanish ground whose surviving character and football continuity make it worth seeking out.', 'NORMAL', NULL, NULL, NULL),
    ('VENUE', NULL, NULL, 23554, NULL, 'CLASSIC_GROUND', 'Classic ground', 'A Spanish ground whose surviving character and football continuity make it worth seeking out.', 'NORMAL', NULL, NULL, NULL),
    ('VENUE', NULL, NULL, 23269, NULL, 'FOOTBALL_LANDMARK', 'Football landmark', 'A venue with exceptional significance in Spanish football history.', 'NORMAL', NULL, NULL, NULL),
    ('VENUE', NULL, NULL, 23260, NULL, 'FOOTBALL_LANDMARK', 'Football landmark', 'A venue with exceptional significance in Spanish football history.', 'NORMAL', NULL, NULL, NULL),
    ('VENUE', NULL, NULL, 23263, NULL, 'FOOTBALL_LANDMARK', 'Football landmark', 'A venue with exceptional significance in Spanish football history.', 'NORMAL', NULL, NULL, NULL),
    ('VENUE', NULL, NULL, 23262, NULL, 'FOOTBALL_LANDMARK', 'Football landmark', 'A venue with exceptional significance in Spanish football history.', 'NORMAL', NULL, NULL, NULL),
    ('VENUE', NULL, NULL, 23564, NULL, 'FOOTBALL_LANDMARK', 'Football landmark', 'A venue with exceptional significance in Spanish football history.', 'NORMAL', NULL, NULL, NULL),
    ('VENUE', NULL, NULL, 23265, NULL, 'FOOTBALL_LANDMARK', 'Football landmark', 'A venue with exceptional significance in Spanish football history.', 'NORMAL', NULL, NULL, NULL),
    ('VENUE', NULL, NULL, 23554, NULL, 'UNIQUE_SETTING', 'Eibar hillside setting', 'A compact football ground squeezed into Eibar''s steep, dense Basque urban landscape.', 'LEAD', NULL, NULL, NULL),
    ('VENUE', NULL, NULL, 23276, NULL, 'UNIQUE_SETTING', 'Vallecas neighbourhood setting', 'A football ground embedded directly into the identity and streets of Vallecas.', 'LEAD', NULL, NULL, NULL),
    ('TEAM_PAIR', 489, 505, NULL, NULL, 'SIGNIFICANT_RIVALRY', 'Derby della Madonnina', 'A genuine Italian rivalry fixture with matchgoing context worth surfacing.', 'NORMAL', NULL, NULL, NULL),
    ('TEAM_PAIR', 487, 497, NULL, NULL, 'SIGNIFICANT_RIVALRY', 'Derby della Capitale', 'A genuine Italian rivalry fixture with matchgoing context worth surfacing.', 'NORMAL', NULL, NULL, NULL),
    ('TEAM_PAIR', 496, 505, NULL, NULL, 'SIGNIFICANT_RIVALRY', 'Derby d''Italia', 'A genuine Italian rivalry fixture with matchgoing context worth surfacing.', 'NORMAL', NULL, NULL, NULL),
    ('TEAM_PAIR', 496, 503, NULL, NULL, 'SIGNIFICANT_RIVALRY', 'Derby della Mole', 'A genuine Italian rivalry fixture with matchgoing context worth surfacing.', 'NORMAL', NULL, NULL, NULL),
    ('TEAM_PAIR', 495, 498, NULL, NULL, 'SIGNIFICANT_RIVALRY', 'Derby della Lanterna', 'A genuine Italian rivalry fixture with matchgoing context worth surfacing.', 'NORMAL', NULL, NULL, NULL),
    ('TEAM_PAIR', 492, 497, NULL, NULL, 'SIGNIFICANT_RIVALRY', 'Southern rivalry', 'A genuine Italian rivalry fixture with matchgoing context worth surfacing.', 'NORMAL', NULL, NULL, NULL),
    ('TEAM_PAIR', 496, 502, NULL, NULL, 'SIGNIFICANT_RIVALRY', 'Historic rivalry', 'A genuine Italian rivalry fixture with matchgoing context worth surfacing.', 'NORMAL', NULL, NULL, NULL),
    ('TEAM_PAIR', 500, 523, NULL, NULL, 'SIGNIFICANT_RIVALRY', 'Emilia rivalry', 'A genuine Italian rivalry fixture with matchgoing context worth surfacing.', 'NORMAL', NULL, NULL, NULL),
    ('TEAM_PAIR', 500, 502, NULL, NULL, 'SIGNIFICANT_RIVALRY', 'Apennine rivalry', 'A genuine Italian rivalry fixture with matchgoing context worth surfacing.', 'NORMAL', NULL, NULL, NULL),
    ('TEAM_PAIR', 504, 1584, NULL, NULL, 'SIGNIFICANT_RIVALRY', 'Veneto rivalry', 'A genuine Italian rivalry fixture with matchgoing context worth surfacing.', 'NORMAL', NULL, NULL, NULL),
    ('TEAM_PAIR', 801, 868, NULL, NULL, 'SIGNIFICANT_RIVALRY', 'Tuscan Derby', 'A genuine Italian rivalry fixture with matchgoing context worth surfacing.', 'NORMAL', NULL, NULL, NULL),
    ('TEAM_PAIR', 515, 801, NULL, NULL, 'SIGNIFICANT_RIVALRY', 'Regional rivalry', 'A genuine Italian rivalry fixture with matchgoing context worth surfacing.', 'NORMAL', NULL, NULL, NULL),
    ('TEAM_PAIR', 523, 880, NULL, NULL, 'SIGNIFICANT_RIVALRY', 'Emilia derby', 'A genuine Italian rivalry fixture with matchgoing context worth surfacing.', 'NORMAL', NULL, NULL, NULL),
    ('TEAM_PAIR', 500, 899, NULL, NULL, 'SIGNIFICANT_RIVALRY', 'Emilia rivalry', 'A genuine Italian rivalry fixture with matchgoing context worth surfacing.', 'NORMAL', NULL, NULL, NULL),
    ('TEAM_PAIR', 880, 899, NULL, NULL, 'SIGNIFICANT_RIVALRY', 'Emilia derby', 'A genuine Italian rivalry fixture with matchgoing context worth surfacing.', 'NORMAL', NULL, NULL, NULL),
    ('TEAM_PAIR', 870, 1584, NULL, NULL, 'SIGNIFICANT_RIVALRY', 'Veneto rivalry', 'A genuine Italian rivalry fixture with matchgoing context worth surfacing.', 'NORMAL', NULL, NULL, NULL),
    ('VENUE', NULL, NULL, 23104, NULL, 'CLASSIC_GROUND', 'Classic ground', 'A surviving Italian football experience with distinctive history, structure or neighbourhood character.', 'NORMAL', NULL, NULL, NULL),
    ('VENUE', NULL, NULL, 23107, NULL, 'CLASSIC_GROUND', 'Classic ground', 'A surviving Italian football experience with distinctive history, structure or neighbourhood character.', 'NORMAL', NULL, NULL, NULL),
    ('VENUE', NULL, NULL, 23108, NULL, 'CLASSIC_GROUND', 'Classic ground', 'A surviving Italian football experience with distinctive history, structure or neighbourhood character.', 'NORMAL', NULL, NULL, NULL),
    ('VENUE', NULL, NULL, 23100, NULL, 'CLASSIC_GROUND', 'Classic ground', 'A surviving Italian football experience with distinctive history, structure or neighbourhood character.', 'NORMAL', NULL, NULL, NULL),
    ('VENUE', NULL, NULL, 23098, NULL, 'CLASSIC_GROUND', 'Classic ground', 'A surviving Italian football experience with distinctive history, structure or neighbourhood character.', 'NORMAL', NULL, NULL, NULL),
    ('VENUE', NULL, NULL, 23112, NULL, 'CLASSIC_GROUND', 'Classic ground', 'A surviving Italian football experience with distinctive history, structure or neighbourhood character.', 'NORMAL', NULL, NULL, NULL),
    ('VENUE', NULL, NULL, 23122, NULL, 'CLASSIC_GROUND', 'Classic ground', 'A surviving Italian football experience with distinctive history, structure or neighbourhood character.', 'NORMAL', NULL, NULL, NULL),
    ('VENUE', NULL, NULL, 23113, NULL, 'CLASSIC_GROUND', 'Classic ground', 'A surviving Italian football experience with distinctive history, structure or neighbourhood character.', 'NORMAL', NULL, NULL, NULL),
    ('VENUE', NULL, NULL, 23125, NULL, 'CLASSIC_GROUND', 'Classic ground', 'A surviving Italian football experience with distinctive history, structure or neighbourhood character.', 'NORMAL', NULL, NULL, NULL),
    ('VENUE', NULL, NULL, 23100, NULL, 'FOOTBALL_LANDMARK', 'Football landmark', 'A venue with exceptional significance in Italian football history.', 'NORMAL', NULL, NULL, NULL),
    ('VENUE', NULL, NULL, 23098, NULL, 'FOOTBALL_LANDMARK', 'Football landmark', 'A venue with exceptional significance in Italian football history.', 'NORMAL', NULL, NULL, NULL),
    ('VENUE', NULL, NULL, 23104, NULL, 'FOOTBALL_LANDMARK', 'Football landmark', 'A venue with exceptional significance in Italian football history.', 'NORMAL', NULL, NULL, NULL),
    ('VENUE', NULL, NULL, 23107, NULL, 'FOOTBALL_LANDMARK', 'Football landmark', 'A venue with exceptional significance in Italian football history.', 'NORMAL', NULL, NULL, NULL),
    ('VENUE', NULL, NULL, 23108, NULL, 'FOOTBALL_LANDMARK', 'Football landmark', 'A venue with exceptional significance in Italian football history.', 'NORMAL', NULL, NULL, NULL),
    ('VENUE', NULL, NULL, 23102, NULL, 'FOOTBALL_LANDMARK', 'Football landmark', 'A venue with exceptional significance in Italian football history.', 'NORMAL', NULL, NULL, NULL),
    ('VENUE', NULL, NULL, 23104, NULL, 'UNIQUE_SETTING', 'Marassi neighbourhood setting', 'A historic football ground tightly embedded in Genoa''s dense Marassi neighbourhood.', 'NORMAL', NULL, NULL, NULL),
    ('TEAM_PAIR', 81, 85, NULL, NULL, 'SIGNIFICANT_RIVALRY', 'Le Classique', 'A genuine French derby or regional rivalry worth surfacing when the fixture occurs.', 'NORMAL', NULL, NULL, NULL),
    ('TEAM_PAIR', 80, 1063, NULL, NULL, 'SIGNIFICANT_RIVALRY', 'Rhône derby', 'A genuine French derby or regional rivalry worth surfacing when the fixture occurs.', 'NORMAL', NULL, NULL, NULL),
    ('TEAM_PAIR', 79, 116, NULL, NULL, 'SIGNIFICANT_RIVALRY', 'Derby du Nord', 'A genuine French derby or regional rivalry worth surfacing when the fixture occurs.', 'NORMAL', NULL, NULL, NULL),
    ('TEAM_PAIR', 84, 91, NULL, NULL, 'SIGNIFICANT_RIVALRY', 'Côte d''Azur Derby', 'A genuine French derby or regional rivalry worth surfacing when the fixture occurs.', 'NORMAL', NULL, NULL, NULL),
    ('TEAM_PAIR', 83, 94, NULL, NULL, 'SIGNIFICANT_RIVALRY', 'Western rivalry', 'A genuine French derby or regional rivalry worth surfacing when the fixture occurs.', 'NORMAL', NULL, NULL, NULL),
    ('TEAM_PAIR', 80, 81, NULL, NULL, 'SIGNIFICANT_RIVALRY', 'Olympico', 'A genuine French derby or regional rivalry worth surfacing when the fixture occurs.', 'NORMAL', NULL, NULL, NULL),
    ('TEAM_PAIR', 85, 114, NULL, NULL, 'SIGNIFICANT_RIVALRY', 'Paris Derby', 'A genuine French derby or regional rivalry worth surfacing when the fixture occurs.', 'NORMAL', NULL, NULL, NULL),
    ('TEAM_PAIR', 102, 112, NULL, NULL, 'SIGNIFICANT_RIVALRY', 'Lorraine Derby', 'A genuine French derby or regional rivalry worth surfacing when the fixture occurs.', 'NORMAL', NULL, NULL, NULL),
    ('TEAM_PAIR', 95, 112, NULL, NULL, 'SIGNIFICANT_RIVALRY', 'Eastern rivalry', 'A genuine French derby or regional rivalry worth surfacing when the fixture occurs.', 'NORMAL', NULL, NULL, NULL),
    ('TEAM_PAIR', 88, 111, NULL, NULL, 'SIGNIFICANT_RIVALRY', 'Normandy Derby', 'A genuine French derby or regional rivalry worth surfacing when the fixture occurs.', 'NORMAL', NULL, NULL, NULL),
    ('TEAM_PAIR', 111, 3221, NULL, NULL, 'SIGNIFICANT_RIVALRY', 'Normandy Derby', 'A genuine French derby or regional rivalry worth surfacing when the fixture occurs.', 'NORMAL', NULL, NULL, NULL),
    ('TEAM_PAIR', 89, 108, NULL, NULL, 'SIGNIFICANT_RIVALRY', 'Burgundy rivalry', 'A genuine French derby or regional rivalry worth surfacing when the fixture occurs.', 'NORMAL', NULL, NULL, NULL),
    ('TEAM_PAIR', 84, 9932, NULL, NULL, 'SIGNIFICANT_RIVALRY', 'Côte d''Azur rivalry', 'A genuine French derby or regional rivalry worth surfacing when the fixture occurs.', 'NORMAL', NULL, NULL, NULL),
    ('TEAM_PAIR', 84, 1305, NULL, NULL, 'SIGNIFICANT_RIVALRY', 'Mediterranean rivalry', 'A genuine French derby or regional rivalry worth surfacing when the fixture occurs.', 'NORMAL', NULL, NULL, NULL),
    ('TEAM_PAIR', 433, 1298, NULL, NULL, 'SIGNIFICANT_RIVALRY', 'Western rivalry', 'A genuine French derby or regional rivalry worth surfacing when the fixture occurs.', 'NORMAL', NULL, NULL, NULL),
    ('TEAM_PAIR', 90, 106, NULL, NULL, 'SIGNIFICANT_RIVALRY', 'Brittany rivalry', 'A genuine French derby or regional rivalry worth surfacing when the fixture occurs.', 'NORMAL', NULL, NULL, NULL),
    ('TEAM_PAIR', 90, 94, NULL, NULL, 'SIGNIFICANT_RIVALRY', 'Brittany rivalry', 'A genuine French derby or regional rivalry worth surfacing when the fixture occurs.', 'NORMAL', NULL, NULL, NULL),
    ('TEAM_PAIR', 1299, 1304, NULL, NULL, 'SIGNIFICANT_RIVALRY', 'Northern coastal rivalry', 'A genuine French derby or regional rivalry worth surfacing when the fixture occurs.', 'NORMAL', NULL, NULL, NULL),
    ('TEAM_PAIR', 101, 3012, NULL, NULL, 'SIGNIFICANT_RIVALRY', 'Alpine rivalry', 'A genuine French derby or regional rivalry worth surfacing when the fixture occurs.', 'NORMAL', NULL, NULL, NULL),
    ('TEAM_PAIR', 89, 115, NULL, NULL, 'SIGNIFICANT_RIVALRY', 'Eastern rivalry', 'A genuine French derby or regional rivalry worth surfacing when the fixture occurs.', 'NORMAL', NULL, NULL, NULL),
    ('TEAM_PAIR', 93, 110, NULL, NULL, 'SIGNIFICANT_RIVALRY', 'Champagne rivalry', 'A genuine French derby or regional rivalry worth surfacing when the fixture occurs.', 'NORMAL', NULL, NULL, NULL),
    ('TEAM_PAIR', 88, 3221, NULL, NULL, 'SIGNIFICANT_RIVALRY', 'Normandy rivalry', 'A genuine French derby or regional rivalry worth surfacing when the fixture occurs.', 'NORMAL', NULL, NULL, NULL),
    ('TEAM_PAIR', 431, 3221, NULL, NULL, 'SIGNIFICANT_RIVALRY', 'Rouen derby', 'A genuine French derby or regional rivalry worth surfacing when the fixture occurs.', 'NORMAL', NULL, NULL, NULL),
    ('VENUE', NULL, NULL, 23035, NULL, 'CLASSIC_GROUND', 'Classic ground', 'A French football ground with surviving character, continuity and a distinctive matchday identity.', 'NORMAL', NULL, NULL, NULL),
    ('VENUE', NULL, NULL, 23296, NULL, 'CLASSIC_GROUND', 'Classic ground', 'A French football ground with surviving character, continuity and a distinctive matchday identity.', 'NORMAL', NULL, NULL, NULL),
    ('VENUE', NULL, NULL, 23288, NULL, 'CLASSIC_GROUND', 'Classic ground', 'A French football ground with surviving character, continuity and a distinctive matchday identity.', 'NORMAL', NULL, NULL, NULL),
    ('VENUE', NULL, NULL, 23291, NULL, 'CLASSIC_GROUND', 'Classic ground', 'A French football ground with surviving character, continuity and a distinctive matchday identity.', 'NORMAL', NULL, NULL, NULL),
    ('VENUE', NULL, NULL, 23292, NULL, 'CLASSIC_GROUND', 'Classic ground', 'A French football ground with surviving character, continuity and a distinctive matchday identity.', 'NORMAL', NULL, NULL, NULL),
    ('VENUE', NULL, NULL, 23027, NULL, 'CLASSIC_GROUND', 'Classic ground', 'A French football ground with surviving character, continuity and a distinctive matchday identity.', 'NORMAL', NULL, NULL, NULL),
    ('VENUE', NULL, NULL, 23290, NULL, 'CLASSIC_GROUND', 'Classic ground', 'A French football ground with surviving character, continuity and a distinctive matchday identity.', 'NORMAL', NULL, NULL, NULL),
    ('VENUE', NULL, NULL, 23031, NULL, 'CLASSIC_GROUND', 'Classic ground', 'A French football ground with surviving character, continuity and a distinctive matchday identity.', 'NORMAL', NULL, NULL, NULL),
    ('VENUE', NULL, NULL, 23285, NULL, 'FOOTBALL_LANDMARK', 'Football landmark', 'A venue with exceptional significance in French football history.', 'NORMAL', NULL, NULL, NULL),
    ('VENUE', NULL, NULL, 23035, NULL, 'FOOTBALL_LANDMARK', 'Football landmark', 'A venue with exceptional significance in French football history.', 'NORMAL', NULL, NULL, NULL),
    ('VENUE', NULL, NULL, 23296, NULL, 'FOOTBALL_LANDMARK', 'Football landmark', 'A venue with exceptional significance in French football history.', 'NORMAL', NULL, NULL, NULL),
    ('VENUE', NULL, NULL, 23288, NULL, 'FOOTBALL_LANDMARK', 'Football landmark', 'A venue with exceptional significance in French football history.', 'NORMAL', NULL, NULL, NULL),
    ('VENUE', NULL, NULL, 23292, NULL, 'FOOTBALL_LANDMARK', 'Football landmark', 'A venue with exceptional significance in French football history.', 'NORMAL', NULL, NULL, NULL),
    ('VENUE', NULL, NULL, 23286, NULL, 'UNIQUE_SETTING', 'Monaco setting', 'A major football ground embedded into the tiny, exceptionally dense principality of Monaco.', 'LEAD', NULL, NULL, NULL);

DO $$
BEGIN
    IF (SELECT count(*) FROM decide_approved_catalogue) <> 217 THEN
        RAISE EXCEPTION 'DECIDE approved catalogue row-count mismatch';
    END IF;
    IF EXISTS (
        SELECT 1 FROM decide_approved_catalogue approved
        WHERE (approved.subject_type = 'TEAM' AND NOT EXISTS (SELECT 1 FROM teams WHERE team_id = approved.team_id))
           OR (approved.subject_type = 'TEAM_PAIR' AND (
               NOT EXISTS (SELECT 1 FROM teams WHERE team_id = approved.team_a_id)
               OR NOT EXISTS (SELECT 1 FROM teams WHERE team_id = approved.team_b_id)))
           OR (approved.subject_type = 'VENUE' AND NOT EXISTS (SELECT 1 FROM venues WHERE venue_id = approved.venue_id))
    ) THEN
        RAISE EXCEPTION 'DECIDE approved catalogue canonical identity mismatch';
    END IF;
END $$;

INSERT INTO decision_facts (
    subject_type, team_a_id, team_b_id, venue_id, team_id, attribute_key, label, explanation,
    publication_status, confidence, lead_priority, reviewed_at, reviewed_by
)
SELECT subject_type, team_a_id, team_b_id, venue_id, team_id, attribute_key, label, explanation,
       'PUBLISHED', 'HIGH', lead_priority, '2026-09-03T00:00:00Z',
       'Matchgoer five-country editorial inventory v0.1'
FROM decide_approved_catalogue
ON CONFLICT DO NOTHING;

INSERT INTO decision_evidence (
    fact_id, source_title, source_url, evidence_note, disposition, retrieved_at, reviewed_at, review_status
)
SELECT fact.fact_id, 'Approved five-country DECIDE inventory evidence', approved.evidence_url,
       coalesce(nullif(approved.evidence_note, ''), 'Evidence retained from approved editorial inventory.'),
       'SUPPORTS', '2026-09-03', '2026-09-03T00:00:00Z', 'ACCEPTED'
FROM decide_approved_catalogue approved
JOIN decision_facts fact ON fact.subject_type = approved.subject_type
 AND fact.attribute_key = approved.attribute_key
 AND fact.team_a_id IS NOT DISTINCT FROM approved.team_a_id
 AND fact.team_b_id IS NOT DISTINCT FROM approved.team_b_id
 AND fact.venue_id IS NOT DISTINCT FROM approved.venue_id
 AND fact.team_id IS NOT DISTINCT FROM approved.team_id
WHERE approved.evidence_url IS NOT NULL
  AND NOT EXISTS (
      SELECT 1 FROM decision_evidence evidence
      WHERE evidence.fact_id = fact.fact_id AND evidence.source_url = approved.evidence_url
  );

DO $$
DECLARE reconciled integer;
BEGIN
    SELECT count(*) INTO reconciled
    FROM decide_approved_catalogue approved
    JOIN decision_facts fact ON fact.subject_type = approved.subject_type
     AND fact.attribute_key = approved.attribute_key
     AND fact.team_a_id IS NOT DISTINCT FROM approved.team_a_id
     AND fact.team_b_id IS NOT DISTINCT FROM approved.team_b_id
     AND fact.venue_id IS NOT DISTINCT FROM approved.venue_id
     AND fact.team_id IS NOT DISTINCT FROM approved.team_id
     AND fact.publication_status = 'PUBLISHED';
    IF reconciled <> 217 THEN
        RAISE EXCEPTION 'DECIDE publication reconciliation failed: expected 217, found %', reconciled;
    END IF;
END $$;

COMMIT;
