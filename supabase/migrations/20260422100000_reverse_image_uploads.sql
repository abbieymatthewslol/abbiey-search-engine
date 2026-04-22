-- reverse_image_uploads
--
-- Private Supabase Storage bucket used by /api/reverse-image to host user
-- uploads for ~1 minute so Bing's reverse-image HTML endpoint can fetch them.
-- Kept PRIVATE: access is only possible through short-lived signed URLs that
-- the Flask server mints with the service role key in reverse_image_storage.py.
--
-- A daily pg_cron job sweeps anything older than 10 minutes so that a crashed
-- request cannot leave orphan blobs lying around.

insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values (
    'reverse-image-uploads',
    'reverse-image-uploads',
    false,
    4194304, -- 4 MB
    array[
        'image/jpeg',
        'image/png',
        'image/gif',
        'image/webp',
        'image/avif'
    ]::text[]
)
on conflict (id) do update set
    public = excluded.public,
    file_size_limit = excluded.file_size_limit,
    allowed_mime_types = excluded.allowed_mime_types;

-- RLS: only the service role talks to this bucket. Anon + authenticated
-- roles never read directly; they always go through signed URLs.
do $$ begin
    create policy "reverse_image_uploads_service_role_all"
        on storage.objects
        for all
        to service_role
        using (bucket_id = 'reverse-image-uploads')
        with check (bucket_id = 'reverse-image-uploads');
exception when duplicate_object then null; end $$;

-- Safety-net cron: delete anything older than 10 minutes. Requires pg_cron.
-- If pg_cron isn't available (local Supabase stack, older projects) this whole
-- block is a no-op; the migration still succeeds.
do $$
declare
    has_cron boolean;
begin
    select exists (
        select 1 from pg_extension where extname = 'pg_cron'
    ) into has_cron;

    if has_cron then
        perform cron.unschedule('reverse_image_uploads_sweeper')
        from cron.job
        where jobname = 'reverse_image_uploads_sweeper';

        perform cron.schedule(
            'reverse_image_uploads_sweeper',
            '*/5 * * * *',
            $sql$
                delete from storage.objects
                where bucket_id = 'reverse-image-uploads'
                  and created_at < now() - interval '10 minutes';
            $sql$
        );
    end if;
end $$;
