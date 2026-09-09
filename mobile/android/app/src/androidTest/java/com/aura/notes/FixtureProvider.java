package com.aura.notes;

import android.content.ContentProvider;
import android.content.ContentValues;
import android.database.Cursor;
import android.database.MatrixCursor;
import android.net.Uri;
import android.os.ParcelFileDescriptor;
import android.provider.OpenableColumns;
import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.FileInputStream;
import java.io.FileNotFoundException;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.util.Arrays;
import java.util.HashSet;
import java.util.Set;

/**
 * Test APK only: fixed public assets, read-only descriptors, no user paths.
 *
 * This provider runs in the test APK's own process. It deliberately uses only
 * Android/Java APIs: that process cannot load Kotlin dependencies supplied by
 * the target APK to the instrumentation process.
 */
public final class FixtureProvider extends ContentProvider {
    private static final int MAX_BYTES = 64 * 1024;
    private static final Set<String> NAMES = new HashSet<>(Arrays.asList(
            "journal-0.aura", "journal-0.physical.ack3", "journal-2.aura",
            "journal-2.physical.ack3", "recorder-1.aura", "recorder-1.physical.ack3",
            "capture-20ms-open.aura", "corrupt-journal-0.aura"));

    @Override public boolean onCreate() { return true; }

    private String name(Uri uri) throws FileNotFoundException {
        if (!"content".equals(uri.getScheme()) ||
                !"com.aura.notes.tests.fixtures".equals(uri.getAuthority()) ||
                uri.getPathSegments().size() != 1 || uri.getQuery() != null ||
                uri.getFragment() != null || !NAMES.contains(uri.getLastPathSegment())) {
            throw new FileNotFoundException("Unknown synthetic test fixture");
        }
        return uri.getLastPathSegment();
    }

    private byte[] readBounded(InputStream input) throws IOException {
        ByteArrayOutputStream output = new ByteArrayOutputStream();
        byte[] buffer = new byte[4096];
        int count;
        while ((count = input.read(buffer)) != -1) {
            if (count == 0) throw new IOException("Synthetic fixture read stalled");
            if (output.size() > MAX_BYTES - count) {
                throw new IOException("Test fixture exceeds provider bound");
            }
            output.write(buffer, 0, count);
        }
        return output.toByteArray();
    }

    private byte[] bytes(String name) throws IOException {
        if (getContext() == null) throw new IOException("Fixture context unavailable");
        String asset = "corrupt-journal-0.aura".equals(name) ? "journal-0.aura" : name;
        byte[] data;
        try (InputStream input = getContext().getAssets().open("fixtures/" + asset)) {
            data = readBounded(input);
        }
        if ("corrupt-journal-0.aura".equals(name)) {
            if (data.length <= 90) throw new IOException("Synthetic fixture is too short");
            data[90] ^= 1;
        }
        return data;
    }

    @Override public synchronized ParcelFileDescriptor openFile(Uri uri, String mode)
            throws FileNotFoundException {
        if (!"r".equals(mode)) throw new FileNotFoundException("Synthetic fixtures are read-only");
        String name = name(uri);
        try {
            byte[] data = bytes(name);
            File directory = new File(getContext().getCacheDir(), "public-instrumentation-fixtures");
            if (!directory.isDirectory() && !directory.mkdirs()) {
                throw new IOException("Could not create synthetic fixture directory");
            }
            File file = new File(directory, name);
            if (file.exists()) {
                if (!file.isFile() || file.length() > MAX_BYTES) {
                    throw new IOException("Cached synthetic fixture differs");
                }
                try (InputStream input = new FileInputStream(file)) {
                    if (!Arrays.equals(readBounded(input), data)) {
                        throw new IOException("Cached synthetic fixture differs");
                    }
                }
            } else {
                if (!file.createNewFile()) throw new IOException("Could not create synthetic fixture");
                try (FileOutputStream output = new FileOutputStream(file)) {
                    output.write(data);
                    output.getFD().sync();
                }
            }
            return ParcelFileDescriptor.open(file, ParcelFileDescriptor.MODE_READ_ONLY);
        } catch (IOException error) {
            FileNotFoundException failure = new FileNotFoundException("Synthetic fixture unavailable");
            failure.initCause(error);
            throw failure;
        }
    }

    @Override public Cursor query(Uri uri, String[] projection, String selection,
                                  String[] selectionArgs, String sortOrder) {
        if (selection != null || selectionArgs != null || sortOrder != null) {
            throw new IllegalArgumentException("Synthetic fixture query does not accept filters");
        }
        try {
            String name = name(uri);
            String[] columns = projection == null
                    ? new String[] { OpenableColumns.DISPLAY_NAME, OpenableColumns.SIZE }
                    : projection;
            if (columns.length > 2) throw new IllegalArgumentException("Too many synthetic fixture columns");
            Object[] values = new Object[columns.length];
            for (int i = 0; i < columns.length; i++) {
                if (OpenableColumns.DISPLAY_NAME.equals(columns[i])) {
                    values[i] = name;
                } else if (OpenableColumns.SIZE.equals(columns[i])) {
                    values[i] = (long) bytes(name).length;
                } else {
                    throw new IllegalArgumentException("Unsupported synthetic fixture column");
                }
            }
            MatrixCursor cursor = new MatrixCursor(columns, 1);
            cursor.addRow(values);
            return cursor;
        } catch (IOException error) {
            throw new IllegalArgumentException("Synthetic fixture unavailable", error);
        }
    }

    @Override public String getType(Uri uri) {
        try {
            name(uri);
            return "application/octet-stream";
        } catch (FileNotFoundException error) {
            throw new IllegalArgumentException("Unknown synthetic test fixture", error);
        }
    }

    @Override public Uri insert(Uri uri, ContentValues values) {
        throw new UnsupportedOperationException("Read-only fixtures");
    }

    @Override public int update(Uri uri, ContentValues values, String selection, String[] selectionArgs) {
        throw new UnsupportedOperationException("Read-only fixtures");
    }

    @Override public int delete(Uri uri, String selection, String[] selectionArgs) {
        throw new UnsupportedOperationException("Read-only fixtures");
    }
}
