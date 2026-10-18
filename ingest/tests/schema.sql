-- tests/schema.sql
CREATE TABLE banks (
	id VARCHAR NOT NULL,
	name VARCHAR NOT NULL,
	PRIMARY KEY (id)
);

CREATE TABLE entities (
	id VARCHAR NOT NULL,
	name VARCHAR NOT NULL,
	province VARCHAR,
	PRIMARY KEY (id)
);

CREATE INDEX ix_entities_province ON entities (province);

CREATE TABLE accounts (
	id VARCHAR NOT NULL,
	bank_id VARCHAR NOT NULL,
	entity_id VARCHAR NOT NULL,
	risk_score NUMERIC,
	risk_category VARCHAR,
	PRIMARY KEY (id),
	FOREIGN KEY(bank_id) REFERENCES banks (id),
	FOREIGN KEY(entity_id) REFERENCES entities (id)
);

CREATE INDEX ix_accounts_entity_id ON accounts (entity_id);

CREATE INDEX ix_accounts_bank_id ON accounts (bank_id);

CREATE INDEX ix_accounts_risk_category ON accounts (risk_category);
