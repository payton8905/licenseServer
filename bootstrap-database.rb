# Run before the API/worker. Never reload the schema of an existing database.
require 'pg'
require 'fileutils'

STDOUT.sync = true
FileUtils.mkdir_p('/runtime')
connection = PG.connect(ENV.fetch('DATABASE_URL'))
begin
  connection.exec('SELECT pg_advisory_lock(1396854093, 1262836046)')
  has_accounts = connection.exec("SELECT to_regclass('public.accounts') IS NOT NULL AS present").first.fetch('present') == 't'
  if has_accounts
    account = connection.exec_params('SELECT id FROM accounts WHERE id=$1', [ENV.fetch('KEYGEN_ACCOUNT_ID')])
    abort 'Existing database does not contain KEYGEN_ACCOUNT_ID. Check .env; existing data was preserved.' if account.ntuples != 1
    command = ['bundle', 'exec', 'rails', 'db:migrate']
    puts 'Existing account found; preserving accounts, credentials and licenses.'
  else
    tables = connection.exec("SELECT count(*) FROM pg_tables WHERE schemaname='public'").first.fetch('count').to_i
    abort 'Database has a partial schema. Inspect .runtime/bootstrap.log; refusing to overwrite existing tables.' unless tables.zero?
    command = ['bundle', 'exec', 'rails', 'keygen:setup']
    puts 'Empty database found; creating schema and configured administrator.'
  end
  File.open('/runtime/bootstrap.log', File::WRONLY | File::CREAT | File::APPEND, 0o600) do |log|
    abort 'Database initialization failed. Inspect .runtime/bootstrap.log locally.' unless system(*command, out: log, err: [:child, :out])
  end
  account = connection.exec_params('SELECT id FROM accounts WHERE id=$1', [ENV.fetch('KEYGEN_ACCOUNT_ID')])
  abort 'Configured account is missing after initialization.' if account.ntuples != 1
  puts 'Database is ready.'
ensure
  connection.close
end
